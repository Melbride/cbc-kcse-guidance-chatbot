
import os
from dotenv import load_dotenv
load_dotenv()
from groq import Groq
from langchain.agents import create_sql_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase


# Load Groq API key from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Groq client directly
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    print(f"Error initializing Groq client: {e}")
    groq_client = None

# Simple SQL query function using Groq
def ask_agent(question: str):
    """
    Ask a question using Groq client instead of LangChain agent
    """
    if not groq_client:
        return "Groq client not available"
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": f"Answer this question about KCSE data: {question}"}],
            temperature=0.0,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    while True:
        q = input("Ask a question (or 'exit'): ")
        if q.lower() == "exit":
            break
        print(ask_agent(q))
