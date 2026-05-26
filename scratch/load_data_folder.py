import os
import sys
import sqlite3
import uuid
import time
from dotenv import load_dotenv

# Add parent directory to path to import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.retriever import WeaviateRetriever

def load_data_from_db():
    load_dotenv()
    
    db_path = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\data\synthetic_sales.db"
    if not os.path.exists(db_path):
        print(f"Error: Database file {db_path} does not exist.")
        return
        
    print("Connecting to Weaviate Cloud...")
    retriever = WeaviateRetriever()
    
    print(f"Opening SQLite database at {db_path}...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    parent_coll = retriever.client.collections.get("RAGParentKnowledge")
    child_coll = retriever.client.collections.get("RAGKnowledge")
    
    batch_size = 1000
    tables = ["customers", "products", "orders", "order_items"]
    
    try:
        for table in tables:
            print(f"\n==========================================")
            print(f"Processing table: {table}")
            print(f"==========================================")
            
            cursor.execute(f"SELECT * FROM {table};")
            rows = cursor.fetchall()
            print(f"Loaded {len(rows)} rows from '{table}' table.")
            
            # Process in batches
            for i in range(0, len(rows), batch_size):
                batch_rows = rows[i : i + batch_size]
                
                parent_objects = []
                child_objects = []
                child_texts = []
                
                for row in batch_rows:
                    row_dict = dict(row)
                    
                    # Map row to text representation, tags, and source based on table schema
                    if table == "customers":
                        p_key = row_dict["customer_id"]
                        text = (
                            f"Customer {row_dict['customer_name']} (ID: {row_dict['customer_id']}) "
                            f"has email {row_dict['email']}. Resides in {row_dict['city']}, "
                            f"{row_dict['state']}, {row_dict['country']}. "
                            f"Segment: {row_dict['customer_segment']}. Signed up on {row_dict['signup_date']}."
                        )
                        source = "customers_table"
                        tags = ["customer", row_dict["customer_segment"], row_dict["country"]]
                        
                    elif table == "products":
                        p_key = row_dict["product_id"]
                        text = (
                            f"Product {row_dict['product_name']} (ID: {row_dict['product_id']}) "
                            f"is in category {row_dict['category']}. Unit price: ${row_dict['unit_price']:.2f}. "
                            f"Supplier: {row_dict['supplier']}. Stock quantity: {row_dict['stock_quantity']} units."
                        )
                        source = "products_table"
                        tags = ["product", row_dict["category"]]
                        
                    elif table == "orders":
                        p_key = row_dict["order_id"]
                        text = (
                            f"Order ID {row_dict['order_id']} was placed on {row_dict['order_date']} "
                            f"by Customer ID {row_dict['customer_id']}. Region: {row_dict['region']}, "
                            f"Channel: {row_dict['sales_channel']}, Payment: {row_dict['payment_method']}, "
                            f"Status: {row_dict['order_status']}. Shipping cost: ${row_dict['shipping_cost']:.2f}."
                        )
                        source = "orders_table"
                        tags = ["order", row_dict["order_status"], row_dict["region"]]
                        
                    elif table == "order_items":
                        p_key = row_dict["order_item_id"]
                        text = (
                            f"Order Item ID {row_dict['order_item_id']} is part of Order ID {row_dict['order_id']}. "
                            f"Product ID: {row_dict['product_id']}, Quantity: {row_dict['quantity']}, "
                            f"Unit price: ${row_dict['unit_price']:.2f}, Discount: {row_dict['discount_percent']}%, "
                            f"Total price: ${row_dict['total_price']:.2f}."
                        )
                        source = "order_items_table"
                        tags = ["order_item", f"order_{row_dict['order_id']}", f"product_{row_dict['product_id']}"]
                    
                    # Generate deterministic UUIDs using table name and primary key
                    parent_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"parent_{table}_{p_key}")
                    child_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"child_{table}_{p_key}")
                    
                    parent_objects.append({
                        "uuid": parent_uuid,
                        "properties": {"text": text, "source": source}
                    })
                    
                    child_texts.append(text)
                    child_objects.append({
                        "uuid": child_uuid,
                        "parent_uuid": parent_uuid,
                        "properties": {
                            "text": text,
                            "tags": tags,
                            "source": source
                        }
                    })
                
                # Generate embeddings for child texts
                t_embed_start = time.time()
                embeddings = retriever.embedding_model.encode(child_texts)
                t_embed_end = time.time()
                
                # Insert parents
                t_parent_start = time.time()
                def _insert_parents():
                    with parent_coll.batch.dynamic() as batch:
                        for p in parent_objects:
                            batch.add_object(
                                properties=p["properties"],
                                uuid=p["uuid"]
                            )
                        batch.flush()
                        failed = parent_coll.batch.failed_objects
                        if failed:
                            raise Exception(f"Failed to insert parents: {failed[0].message}")
                retriever.execute_with_retry(_insert_parents)
                t_parent_end = time.time()
                
                # Insert children pointing to parents
                t_child_start = time.time()
                def _insert_children():
                    with child_coll.batch.dynamic() as batch:
                        for idx, c in enumerate(child_objects):
                            batch.add_object(
                                properties=c["properties"],
                                vector=embeddings[idx].tolist() if hasattr(embeddings[idx], "tolist") else embeddings[idx],
                                uuid=c["uuid"],
                                references={"parent": c["parent_uuid"]}
                            )
                        batch.flush()
                        failed = child_coll.batch.failed_objects
                        if failed:
                            raise Exception(f"Failed to insert children: {failed[0].message}")
                retriever.execute_with_retry(_insert_children)
                t_child_end = time.time()
                
                print(
                    f"Batch {i//batch_size + 1}/{(len(rows)-1)//batch_size + 1} completed: "
                    f"Embed={t_embed_end-t_embed_start:.2f}s, ParentInsert={t_parent_end-t_parent_start:.2f}s, ChildInsert={t_child_end-t_child_start:.2f}s"
                )
                
        print(f"\n==========================================")
        print("Ingestion verification:")
        print(f"==========================================")
        count = retriever.get_count()
        print(f"Total documents in RAGKnowledge collection: {count}")
        sources = retriever.get_sources()
        print(f"Indexed sources: {sources}")
        
    except Exception as e:
        print(f"Error during database loading: {e}")
    finally:
        conn.close()
        retriever.close()
        print("Connection closed.")

if __name__ == "__main__":
    load_data_from_db()
