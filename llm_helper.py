from dotenv import load_dotenv
from langchain_groq import ChatGroq
import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

llm = ChatGroq(groq_api_key=os.getenv("GROQ_API_KEY"), model="meta-llama/llama-4-scout-17b-16e-instruct")

if __name__ == "__main__":
    response = llm.invoke("What are the two main ingradients in samosa")
    print(response.content)
