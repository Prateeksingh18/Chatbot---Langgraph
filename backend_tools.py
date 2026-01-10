from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
from langchain_core.tools import Tool
from langgraph.prebuilt import ToolNode,tools_condition
from dotenv import load_dotenv
# from utilis import search_tool,get_stock_price,calculator
import sqlite3
import os
import requests

load_dotenv()
from langchain_core.tools import tool

@tool
def fetch_github_repo_details(repo_full_name: str) -> str:
    """
    Fetches key details for a specific GitHub repository.
    
    Args:
        repo_full_name: Full repo name like 'owner/repo' (e.g., 'langchain-ai/langchain')
    
    Returns:
        Repo details including name, description, stars, forks, language, and URL.
    """
    print(f" TOOL CALLED: fetch_github_repo_details('{repo_full_name}')")
    try:
        owner, repo = repo_full_name.split('/')
        url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {'Accept': 'application/vnd.github+json'}
        # Optional: Add token for private repos or higher rate limits
        token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
        if token:
            headers['Authorization'] = f'token {token}'
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        return f"""**{data.get('name', 'N/A')}**
        - Description: {data.get('description', 'No description')}
        - Stars: {data.get('stargazers_count', 0)}
        - Forks: {data.get('forks_count', 0)}
        - Language: {data.get('language', 'Unknown')}
        - URL: {data.get('html_url', 'N/A')}"""
        
    except Exception as e:
        return f"Error fetching repo '{repo_full_name}': {str(e)}"

llm = ChatOpenAI(
    api_key=os.getenv("PERPLEXITY_API_KEY"),
    base_url="https://api.perplexity.ai",
    model="sonar-pro",
    temperature=0.1
)

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# Tools initialization
tools = [fetch_github_repo_details]
llm_with_tools = llm.bind_tools(tools)
Tool = ToolNode(tools)

def chat_node(state: ChatState):
    messages = state['messages']
    
    system_prompt = SystemMessage(content="""
    You are a helpful assistant with GitHub tools. 
    
    Use tools when users mention:
    - GitHub repositories, repo details, stars, forks
    - "list repos", "get details for [repo]"
    
    Examples: "Get langchain-ai/langgraph details" → fetch_github_repo_details
    """)
    
    response = llm_with_tools.invoke([system_prompt] + messages)
    return {"messages": [response]}

conn = sqlite3.connect(database='chatbot.db', check_same_thread=False)
# Checkpointer
checkpointer = SqliteSaver(conn=conn)


graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", Tool)

graph.add_edge(START, "chat_node")
graph.add_conditional_edges('chat_node', tools_condition)
graph.add_edge('tools','chat_node')
graph.add_edge("chat_node", END)

chatbot = graph.compile(checkpointer=checkpointer)


def retrieve_all_thread():
    all_threads = set()
    for checkpoint in checkpointer.list(None):
        all_threads.add(checkpoint.config['configurable']['thread_id'])

    return list(all_threads)

