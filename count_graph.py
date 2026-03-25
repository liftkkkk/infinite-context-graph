import json
try:
    with open('c:/Users/z1881/Downloads/infinite/entity_graph.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Nodes: {len(data.get('nodes', []))}")
    print(f"Edges: {len(data.get('edges', []))}")
    
    nodes = data.get('nodes', [])
    nodes.sort(key=lambda x: x.get('importance', 0), reverse=True)
    
    print("\nTop 10 nodes by importance:")
    for i, node in enumerate(nodes[:10]):
        print(f"{i+1}. {node.get('id')} ({node.get('type')}): {node.get('importance', 0):.4f}")
except Exception as e:
    print(f"Error: {e}")
