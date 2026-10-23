import pathlib

file_path = pathlib.Path('dashboard/app.py')
content = file_path.read_text(encoding='utf-8')

# নতুন এন্ডপয়েন্ট তৈরি
new_endpoint = '''
@app.get("/api/position/{symbol}")
def get_position(symbol: str):
    from database import get_conn
    try:
        with get_conn() as c:
            with c.cursor() as cur:
                cur.execute("SELECT side, entry_price, stop_loss, take_profit FROM trades WHERE symbol = %s AND status = 'OPEN' ORDER BY id DESC LIMIT 1", (symbol,))
                row = cur.fetchone()
                if row:
                    return {"has_position": True, "side": row[0], "entry": float(row[1]), "sl": float(row[2]), "tp": float(row[3])}
                return {"has_position": False}
    except Exception as e:
        return {"has_position": False, "error": str(e)}
'''

if 'def get_position' not in content:
    content += new_endpoint
    file_path.write_text(content, encoding='utf-8')
    print('\n[SUCCESS] Backend updated with Position API!\n')
else:
    print('\n[INFO] Backend already updated.\n')
