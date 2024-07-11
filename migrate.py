from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

from dotenv import load_dotenv
import os

load_dotenv()

client = (Client()
    .set_endpoint('https://appwrite.shuchir.dev/v1') # Your API Endpoint
    .set_project('wheresmyflight')                # Your project ID
    .set_key(os.environ['APPWRITE_KEY']))          # Your secret API key
db = Databases(client)

def get_all_docs(data, collection, queries=[]):
    docs = []
    offset = 0
    ogq = queries.copy()
    while True:
        queries = ogq.copy()
        queries.append(Query.offset(offset))
        queries.append(Query.limit(100))
        results = db.list_documents(data, collection, queries=queries)
        if len(docs) == results['total']:
            break
        results = results['documents']
        docs += results
        offset += len(results)
    return docs

flights = get_all_docs('data', 'flights')
passes = get_all_docs('data', 'passes')

userId = "65b8e699a2ea1cfd6d44"

for bpass in passes:
    try:
        db.update_document('data', 'passes', bpass['$id'], {
            "flightId": next(flight for flight in flights if flight['flightId'] == bpass['flightId'])['$id'],
        },
        [
            f'read("user:{userId}")', 
            f'write("user:{userId}")'
        ])
        print(f"Updated bpass {bpass['$id']} with flightId {bpass['flightId']}")
    except: pass