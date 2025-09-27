
import streamlit as st
from langchain_groq import ChatGroq
from langchain_community.utilities import ArxivAPIWrapper, WikipediaAPIWrapper
from langchain_community.tools import ArxivQueryRun, WikipediaQueryRun, DuckDuckGoSearchRun
from langchain.agents import AgentExecutor, create_react_agent
from langchain import hub
from langchain.callbacks import StreamlitCallbackHandler
import os
from dotenv import load_dotenv

# New imports for PDF processing
import pypdf
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.tools.retriever import create_retriever_tool

load_dotenv()

## Arxiv and wikipedia tools
api_wrapper=WikipediaAPIWrapper(top_k_results=1,doc_content_chars_max=250)
wiki=WikipediaQueryRun(api_wrapper=api_wrapper)


arxiv_wrapper=ArxivAPIWrapper(top_k_results=1,doc_content_chars_max=250)
arxiv=ArxivQueryRun(api_wrapper=arxiv_wrapper)

search=DuckDuckGoSearchRun(name="Search")

st.title("Langchain - Chat with search")


## sidebar for settings
st.sidebar.title('Settings')
api_key=st.sidebar.text_input(
    'Enter your Groq API Key',
    type='password',
)

# New: PDF uploader in the sidebar
pdf_doc = st.sidebar.file_uploader(
    "Upload a PDF to chat with",
    type="pdf"
)

# New: Process the PDF and create a retriever if a file is uploaded
if pdf_doc and "pdf_retriever" not in st.session_state:
    with st.spinner("Processing PDF... This may take a moment."):
        # Read the PDF file from the upload
        pdf_reader = pypdf.PdfReader(pdf_doc)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""

        # Split the text into manageable chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        chunks = text_splitter.split_text(text=text)

        # Create embeddings using a free model from HuggingFace
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        vector_store = FAISS.from_texts(chunks, embedding=embeddings)
        st.session_state.pdf_retriever = vector_store.as_retriever()
        st.sidebar.success("PDF processed successfully!")

if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "assistant", "content": "Hi,I'm a chatbot who can search web.How can I help you?"}
    ]
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt:=st.chat_input(placeholder="What is machine learning?"):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # Check if API key is provided
    if not api_key:
        with st.chat_message("assistant"):
            st.error("🔑 **API Key Required**")
            st.info("Please enter your Groq API key in the sidebar to start chatting!")
            st.markdown("""
            **How to get your Groq API key:**
            1. Visit [console.groq.com](https://console.groq.com)
            2. Sign up for a free account
            3. Generate your API key
            4. Paste it in the sidebar above
            """)
            st.session_state.messages.append({
                "role": "assistant", 
                "content": "Please enter your Groq API key in the sidebar to start chatting!"
            })
    else:
        try:
            llm=ChatGroq(groq_api_key=api_key,model_name="llama-3.1-8b-instant",streaming=True)
            
            # Start with the base tools
            tools=[wiki, arxiv, search]

            # New: If the PDF retriever exists in the session, create and add the PDF tool
            if "pdf_retriever" in st.session_state:
                pdf_retriever_tool = create_retriever_tool(
                    st.session_state.pdf_retriever,
                    "pdf_document_search",
                    "Searches and returns information from the uploaded PDF document. You MUST use this tool first to answer questions before trying other tools."
                )
                tools.insert(0, pdf_retriever_tool) # Insert at the beginning to signal priority

            # Get the prompt to use - you can modify this!
            prompt_template = hub.pull("hwchase17/react")

            agent = create_react_agent(llm, tools, prompt_template)
            search_agent = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                handle_parsing_errors=True,
            )

            with st.chat_message("assistant"):
                st_cb=StreamlitCallbackHandler(st.container(),expand_new_thoughts=False)
                response = search_agent.invoke({"input": prompt}, {"callbacks": [st_cb]})
                response_content = response["output"]
                st.session_state.messages.append({"role": "assistant", "content": response_content})
                st.write(response_content)
                
        except Exception as e:
            with st.chat_message("assistant"):
                st.error("🚨 **Oops! Something went wrong**")
                st.warning("There was an error processing your request. Please try again!")
                
                # Show helpful error message based on the error type
                if "api_key" in str(e).lower() or "groq" in str(e).lower():
                    st.info("💡 **Tip:** Make sure your Groq API key is valid and has sufficient credits.")
                elif "rate" in str(e).lower() or "limit" in str(e).lower():
                    st.info("⏰ **Rate Limit:** Please wait a moment before trying again.")
                else:
                    st.info("🔄 **Solution:** Try refreshing the page or check your internet connection.")
                
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": "Sorry, I encountered an error. Please try again!"
                })
