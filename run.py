from operator import not_
import os
import glob
import json
import networkx as nx
import concurrent.futures
from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from modelscope import AutoTokenizer
from pydantic import BaseModel, Field
from typing import List

# Import chunk logic
# Note: Ensure chunk.py is in the same directory
try:
    from chunk import chunk_text, DEFAULT_MODEL_PATH
except ImportError:
    # Fallback if import fails (e.g. name conflict or missing file)
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from chunk import chunk_text, DEFAULT_MODEL_PATH

# Load environment variables
load_dotenv()

# Configuration
API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = "https://api.siliconflow.cn"
MODEL_NAME = "Qwen/Qwen3-8B"
CHUNK_SIZE = 2048  # Adjust based on needs
MAX_WORKERS = 4   # Number of parallel API calls
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data") # Assumes data is in a subfolder 'data' or current folder
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "entity_graph.json")

# Initialize Client
if not API_KEY:
    print("Warning: OPENAI_API_KEY not found in environment variables. Please set it in .env file.")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# Retry Logic (Adapted from app.py)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
def call_openai_with_retry(messages, response_format={"type": "json_object"}):
    return client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        response_format=response_format,
        timeout=60
    )

class EntityList(BaseModel):
    entities: List[str] = Field(description="A list of core entities extracted from the text")

def extract_entities_for_passage(passage):
    """
    Wrapper for entity extraction to be used with ThreadPoolExecutor.
    Returns tuple (passage, entities_list)
    """
    text_chunk = passage['content']
    prompt = f"""
    请分析以下文本片段，并找出其中的核心实体。
    核心实体包括：人名 (Person)、地点 (Location)、组织 (Organization)、事件 (Event) 以及高频名词短语 (High-freq Noun Phrases)。
    
    文本片段:
    {text_chunk}
    
    请严格输出为 JSON 格式，包含一个 'entities' 字段，该字段为字符串列表。
    示例: {{"entities": ["伊隆·马斯克", "特斯拉", "SpaceX", "火星登陆", "电动汽车"]}}
    """
    
    try:
        response = call_openai_with_retry([
            {"role": "system", "content": "你是一个资深信息抽取专家。请只返回符合 schema 的 JSON。"},
            {"role": "user", "content": prompt}
        ])
        content = response.choices[0].message.content
        
        # Validate with Pydantic
        try:
            # First try direct parsing
            result = EntityList.model_validate_json(content)
            entities = result.entities
        except Exception:
            # Fallback for some models that might output markdown code blocks
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = EntityList.model_validate_json(json_match.group(0))
                entities = result.entities
            else:
                raise ValueError("No JSON object found in response")

        return passage, entities
    except Exception as e:
        print(f"Error extracting entities for {passage.get('id', 'unknown')}: {e}")
        return passage, []

def main():
    # 1. Load all markdown files
    # Search in current directory and subdirectories
    search_path = os.path.join(os.getcwd(), "**/*.md")
    if os.path.exists(DATA_DIR):
         search_path = os.path.join(DATA_DIR, "**/*.md")
         
    md_files = glob.glob(search_path, recursive=True)
    
    # Exclude the requirements file and other system files if they are picked up
    exclude_files = ["产品功能.md", "README.md"]
    md_files = [f for f in md_files if os.path.basename(f) not in exclude_files]
    
    if not md_files:
        print("No markdown files found.")
        return

    print(f"Found {len(md_files)} markdown files.")
    
    all_passages = []
    
    # Initialize Tokenizer
    tokenizer = None
    try:
        if os.path.exists(DEFAULT_MODEL_PATH):
            print(f"Loading tokenizer from {DEFAULT_MODEL_PATH}...")
            tokenizer = AutoTokenizer.from_pretrained(DEFAULT_MODEL_PATH)
        else:
            print(f"Warning: Local model path {DEFAULT_MODEL_PATH} not found. Chunking might be slower or use default fallback.")
    except Exception as e:
        print(f"Error loading tokenizer: {e}")

    print("Step 1: Reading and Chunking files...")
    for file_path in md_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
                if not text.strip():
                    continue
                
                # Chunking
                chunks = chunk_text(text, CHUNK_SIZE, tokenizer=tokenizer)
                file_name = os.path.basename(file_path)
                
                for i, chunk in enumerate(chunks):
                    passage_id = f"{file_name}_p{i}"
                    all_passages.append({
                    "id": passage_id,
                    "content": chunk,
                    "source": file_name,
                    "file_path": file_path
                })
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
    
    print(f"Total passages created: {len(all_passages)}")
    
    if not all_passages:
        print("No passages generated. Exiting.")
        return

    # 2. Build Graph
    G = nx.DiGraph()
    
    print(f"Step 2: Extracting Entities and Building Graph (Parallel: {MAX_WORKERS} workers)...")
    
    process_passages = all_passages
    
    from tqdm import tqdm
    
    # Use ThreadPoolExecutor for parallel processing
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_passage = {executor.submit(extract_entities_for_passage, p): p for p in process_passages}
        
        # Process results as they complete
        for future in tqdm(concurrent.futures.as_completed(future_to_passage), total=len(process_passages), desc="Processing Passages"):
            passage, entities = future.result()
            
            passage_node_id = passage['id']
            # Add Passage Node
            # Note: NetworkX graph operations are not thread-safe for complex algos, 
            # but simple add_node/add_edge are generally fine if not deleting simultaneously.
            # Here we are in the main thread loop consuming results, so it is safe.
            G.add_node(passage_node_id, type="passage", content=passage['content'], file=passage['file_path'])
            
            for entity in entities:
                entity = entity.strip()
                if not entity: continue
                
                # Add Entity Node
                if not G.has_node(entity):
                    G.add_node(entity, type="entity")
                
                # Add Edge: Passage -> Entity (mention)
                G.add_edge(passage_node_id, entity, type="mention")
            
    print(f"Graph built with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")

    # 3. Calculate PageRank
    print("Step 3: Calculating PageRank...")
    try:
        if len(G) > 0:
            pagerank_scores = nx.pagerank(G, alpha=0.85)
        else:
            pagerank_scores = {}
    except Exception as e:
        print(f"PageRank failed (possibly convergence error): {e}")
        pagerank_scores = {n: 0 for n in G.nodes()}

    # Assign importance to nodes
    for node in G.nodes():
        G.nodes[node]['importance'] = pagerank_scores.get(node, 0)

    # 4. Check Connectivity and Add Root
    print("Step 4: Handling Connectivity...")
    
    # Add Root Node
    root_id = "root"
    G.add_node(root_id, type="root", importance=1.0)
    
    # Get Weakly Connected Components
    # Note: nx.weakly_connected_components returns sets of nodes
    if len(G) > 1: # Only if we have other nodes
        components = list(nx.weakly_connected_components(G))
        print(f"Found {len(components)} connected components.")
        
        for comp in components:
            if root_id in comp:
                continue # Skip if root is already somehow involved (shouldn't be yet)
                
            # Strategy: Connect root to the most important node in the subgraph
            # We prefer connecting to an 'entity' node if available, otherwise any node
            comp_nodes = list(comp)
            
            # Filter for entity nodes first
            not_entity_nodes = [n for n in comp_nodes if G.nodes[n].get('type') != 'entity']
            
            if not_entity_nodes:
                candidates = not_entity_nodes
            else:
                candidates = comp_nodes
                
            if not candidates:
                continue
                
            best_node = max(candidates, key=lambda n: G.nodes[n].get('importance', 0))
            
            # Add Edge: Root -> Best Node (contain)
            G.add_edge(root_id, best_node, type="related_to")
            # print(f"Connected root to subgraph via '{best_node}'") 

    # 5. Save to JSON
    print("Step 5: Saving to JSON...")
    
    # Prepare JSON structure
    nodes_data = []
    for n in G.nodes():
        node_data = {
            "id": n,
            "type": G.nodes[n].get("type", "unknown"),
            "importance": G.nodes[n].get("importance", 0)
        }
        # Optional: include content for passages
        if "content" in G.nodes[n]:
            node_data["content"] = G.nodes[n]["content"]
        if "file" in G.nodes[n]:
            node_data["file"] = G.nodes[n]["file"]
        nodes_data.append(node_data)
        
    edges_data = []
    for i, (u, v) in enumerate(G.edges()):
        edge_data = {
            "id": f"edge_{i}",
            "source": u,
            "target": v,
            "type": G.edges[u, v].get("type", "unknown")
        }
        edges_data.append(edge_data)
        
    output_data = {
        "nodes": nodes_data,
        "edges": edges_data
    }
    
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"Successfully saved graph to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Error saving JSON: {e}")

if __name__ == "__main__":
    main()
