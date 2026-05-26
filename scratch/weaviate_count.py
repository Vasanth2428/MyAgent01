import os
import weaviate
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("WEAVIATE_URL")
api_key = os.getenv("WEAVIATE_API_KEY")

print("Connecting to Weaviate...")
client = weaviate.connect_to_weaviate_cloud(
    cluster_url=url,
    auth_credentials=weaviate.classes.init.Auth.api_key(api_key)
)

try:
    print("Connected.")
    for name in ["RAGParentKnowledge", "RAGKnowledge"]:
        if client.collections.exists(name):
            coll = client.collections.get(name)
            res = coll.aggregate.over_all(total_count=True)
            print(f"Collection '{name}' total count: {res.total_count}")
        else:
            print(f"Collection '{name}' does not exist.")
finally:
    client.close()
    print("Connection closed.")
