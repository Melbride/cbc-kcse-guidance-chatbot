
import os
from dotenv import load_dotenv
load_dotenv()
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_sql_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase


# Load Gemini API key from environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Set up Gemini LLM for LangChain
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0.0,
)

# Set up SQLDatabase connection (PostgreSQL)
db_uri = os.getenv("DATABASE_URL")  # e.g., "postgresql+psycopg2://user:password@host:port/dbname"
if not db_uri:
    raise ValueError("DATABASE_URL environment variable not set or loaded.")
db = SQLDatabase.from_uri(db_uri)

# Create a toolkit for the agent
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

# Create the agent
agent_executor = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
)

def ask_agent(question: str):
    """
    Ask the LangChain agent a question. Returns the agent's answer as a string.
    """
    return agent_executor.run(question)

if __name__ == "__main__":
    while True:
        q = input("Ask a question (or 'exit'): ")
        if q.lower() == "exit":
            break
        print(ask_agent(q))
