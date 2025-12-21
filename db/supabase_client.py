from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


SUPABASE_URL2 = os.getenv("SUPABASE_URL2")
SUPABASE_KEY2 = os.getenv("SUPABASE_KEY2")

supabase2: Client = create_client(SUPABASE_URL2, SUPABASE_KEY2)