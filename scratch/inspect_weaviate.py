import os
import weaviate
import weaviate.classes as wvc
from weaviate.classes.init import Auth
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("WEAVIATE_URL")
api_key = os.getenv("WEAVIATE_API_KEY")

client = weaviate.connect_to_weaviate_cloud(
    cluster_url=url,
    auth_credentials=Auth.api_key(api_key)
)

try:
    print("Collections list:")
    for name in client.collections.list_all().keys():
        print(f" - {name}")
        coll = client.collections.get(name)
        config = coll.config.get()
        print(f"   Properties:")
        for prop in config.properties:
            print(f"     * {prop.name} ({prop.data_type})")
        print(f"   References:")
        for ref in config.references:
            print(f"     * {ref.name} -> {ref.target_collections}")
finally:
    client.close()
