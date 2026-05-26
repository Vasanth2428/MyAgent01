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
    # Delete if exists
    if client.collections.exists("RAGKnowledge"):
        client.collections.delete("RAGKnowledge")
    if client.collections.exists("RAGParentKnowledge"):
        client.collections.delete("RAGParentKnowledge")

    print("Creating RAGParentKnowledge...")
    parent_coll = client.collections.create(
        name="RAGParentKnowledge",
        vector_config=wvc.config.Configure.Vector.none(),
        properties=[
            wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="source", data_type=wvc.config.DataType.TEXT),
        ]
    )

    print("Creating RAGKnowledge...")
    child_coll = client.collections.create(
        name="RAGKnowledge",
        vector_config=wvc.config.Configure.Vector.none(),
        properties=[
            wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
            wvc.config.Property(name="source", data_type=wvc.config.DataType.TEXT),
        ],
        references=[
            wvc.config.ReferenceProperty(
                name="parent",
                target_collection="RAGParentKnowledge"
            )
        ]
    )

    print("Inserting data...")
    # Insert parent
    p_uuid = parent_coll.data.insert(
        properties={"text": "This is the parent text block that has 1500 tokens.", "source": "test_ref.txt"}
    )
    print(f"Parent inserted: {p_uuid}")

    # Insert child pointing to parent
    c_uuid = child_coll.data.insert(
        properties={
            "text": "This is the child text block.",
            "tags": ["test"],
            "source": "test_ref.txt"
        },
        references={"parent": p_uuid}
    )
    print(f"Child inserted: {c_uuid}")

    # Query child and resolve parent reference
    # In Weaviate v4: query with references is done via query.hybrid or query.fetch_objects using `return_references`
    print("Querying child...")
    from weaviate.classes.query import QueryReference
    res = child_coll.query.fetch_objects(
        limit=1,
        return_references=[
            QueryReference(
                link_on="parent",
                return_properties=["text", "source"]
            )
        ]
    )

    for obj in res.objects:
        print(f"Child text: {obj.properties['text']}")
        if "parent" in obj.references:
            parent_objs = obj.references["parent"].objects
            print(f"Parent reference found: {len(parent_objs)} objects")
            for p_obj in parent_objs:
                print(f"  Parent text: {p_obj.properties['text']}")

finally:
    # Cleanup
    if client.collections.exists("RAGKnowledge"):
        client.collections.delete("RAGKnowledge")
    if client.collections.exists("RAGParentKnowledge"):
        client.collections.delete("RAGParentKnowledge")
    client.close()
