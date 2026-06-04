import socket

def test_connection(host="db.ihuotojtcnmiwdukyxtx.supabase.co", port=5432):
    try:
        socket.create_connection((host, port), timeout=5)
        print("Success! Can reach Supabase.")
    except OSError as e:
        print(f"Failed! Cannot reach Supabase: {e}")

test_connection()