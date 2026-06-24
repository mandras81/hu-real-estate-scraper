#!/usr/bin/env python3
"""Self-contained PostgreSQL admin server - FastAPI + uvicorn"""
import os, sys, json, re
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    os.system("pip3 install psycopg2-binary -q")
    import psycopg2
    import psycopg2.extras

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

DB_ALIASES = {
    "real_estate": "postgresql://openclaw:upwork2026@10.10.10.103:5432/real_estate_scraper",
    "upwork": "postgresql://openclaw:upwork2026@10.10.10.103:5432/upwork_pipeline",
}

def get_db(dsn=None):
    if not dsn: dsn = list(DB_ALIASES.values())[0]
    conn = psycopg2.connect(dsn, connect_timeout=5)
    conn.set_client_encoding("UTF8")
    return conn

app = FastAPI(title="PG Admin")

CSS = """<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#0f172a;color:#e2e8f0;padding:20px;font-size:14px}
h1,h2{color:#f8fafc}
a{color:#38bdf8;text-decoration:none}
.card{background:#1e293b;border-radius:8px;padding:16px;margin:12px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 10px;border-bottom:1px solid #334155;text-align:left}
th{background:#334155;color:#94a3b8}
tr:hover{background:#1e293b}
pre{background:#0f172a;padding:12px;border-radius:6px;overflow:auto;max-height:500px;font-size:12px}
.nav{display:flex;gap:12px;margin:12px 0;flex-wrap:wrap}
.nav a{background:#1e293b;padding:8px 16px;border-radius:6px;border:1px solid #334155}
input,select,textarea{background:#1e293b;color:#e2e8f0;border:1px solid #475569;padding:8px;border-radius:6px;font:13px monospace}
button{background:#38bdf8;color:#0f172a;border:none;padding:8px 20px;border-radius:6px;font-weight:600;cursor:pointer}
code{background:#334155;padding:2px 6px;border-radius:4px}
.bar{display:inline-block;height:10px;border-radius:5px;background:#334155}
.bar-fill{height:100%;border-radius:5px;background:#38bdf8}
.green{color:#86efac}.yellow{color:#fde047}.red{color:#fca5a5}
.badge.ok{background:#166534;color:#86efac;padding:2px 6px;border-radius:4px;font-size:11px}
.badge.warn{background:#854d0e;color:#fde047;padding:2px 6px;border-radius:4px;font-size:11px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px}
.stat{text-align:center;padding:16px;background:#0f172a;border-radius:6px}
.stat-val{font-size:28px;font-weight:700}
.stat-lbl{font-size:11px;color:#94a3b8}
</style>"""

def page(title, body):
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{title}</title>{CSS}</head><body>{body}</body></html>"""

@app.get("/")
async def home():
    db_list = "".join(f'<div class="stat"><div class="stat-val"><a href="/db/{k}">{k}</a></div><div class="stat-lbl">{v.split("@")[-1]}</div></div>' for k,v in DB_ALIASES.items())
    return HTMLResponse(page("PG Admin", f"""
<h1>🐘 PG Admin</h1>
<div class="nav">
  <a href="/">Dashboard</a>
  <a href="/console">SQL Console</a>
  <a href="/connections">Connections</a>
</div>
<div class="grid">{db_list}</div>
"""))

@app.get("/db/{name}")
async def db_page(name: str):
    dsn = DB_ALIASES.get(name)
    if not dsn: return HTMLResponse(page("Error", "<h1>Unknown DB</h1>"))
    try:
        conn = get_db(dsn)
        cur = conn.cursor()
        cur.execute("SELECT version()"); ver = cur.fetchone()[0][:60]
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))"); sz = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM pg_stat_user_tables"); tbl = cur.fetchone()[0]
        cur.execute("""SELECT relname, n_live_tup::int FROM pg_stat_user_tables ORDER BY n_live_tup DESC NULLS LAST""")
        tables = cur.fetchall()
        conn.close()
        
        tbl_html = ""
        for t in tables:
            tbl_html += f"<tr><td><a href='/table/{t[0]}?db={name}'>{t[0]}</a></td><td>{t[1]:,}</td></tr>"
        
        return HTMLResponse(page(f"DB: {name}", f"""
<h1><a href='/' style='color:#94a3b8'>⬅</a> {name}</h1>
<div class="card">
<table><tr><td>Version</td><td>{ver}</td></tr>
<tr><td>Size</td><td>{sz}</td></tr>
<tr><td>Tables</td><td>{tbl}</td></tr></table>
</div>
<div class="card"><h2>Tables</h2><table><tr><th>Name</th><th>Rows</th></tr>{tbl_html}</table></div>
"""))
    except Exception as e:
        return HTMLResponse(page("Error", f"<pre>{e}</pre>"))

@app.get("/table/{table}")
async def table_page(table: str, db: str = "real_estate"):
    dsn = DB_ALIASES.get(db)
    if not dsn: return HTMLResponse(page("Error","Bad DB"))
    try:
        conn = get_db(dsn)
        cur = conn.cursor()
        cur.execute(f'SELECT count(*) FROM "{table}"')
        count = cur.fetchone()[0]
        
        cur.execute(f'SELECT * FROM "{table}" ORDER BY 1 DESC LIMIT 50')
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        conn.close()
        
        thead = "<tr>"+"".join(f"<th>{c}</th>" for c in cols)+"</tr>"
        tbody = ""
        for r in rows:
            vals = [str(c)[:80] for c in r]
            tbody += "<tr>"+"".join(f"<td>{v}</td>" for v in vals)+"</tr>"
        
        return HTMLResponse(page(f"Table: {table}", f"""
<h1><a href='/db/{db}' style='color:#94a3b8'>⬅</a> {table}</h1>
<div class="card"><p>{count:,} rows, {len(cols)} columns</p></div>
<div class="card"><table>{thead}{tbody}</table></div>
"""))
    except Exception as e:
        return HTMLResponse(page("Error", f"<pre>{e}</pre>"))

@app.get("/console")
async def console(db: str = "real_estate", q: str = ""):
    db_sel = "".join(f"<option value='{k}' {'selected' if k==db else ''}>{k}</option>" for k in DB_ALIASES)
    result = ""
    
    if q:
        dsn = DB_ALIASES.get(db)
        try:
            conn = get_db(dsn)
            conn.set_session(autocommit=True)
            cur = conn.cursor()
            cur.execute(q)
            if cur.description:
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchmany(500)
                thead = "<tr>"+"".join(f"<th>{c}</th>" for c in cols)+"</tr>"
                tbody = ""
                for r in rows:
                    vals = [str(c)[:100] for c in r]
                    tbody += "<tr>"+"".join(f"<td>{v}</td>" for v in vals)+"</tr>"
                result = f'<div class="card"><table>{thead}{tbody}</table><p>{len(rows)} rows</p></div>'
            else:
                result = f'<div class="card"><p>✅ {cur.rowcount} rows affected</p></div>'
        except Exception as e:
            result = f'<div class="card"><p class="red">❌ {e}</p></div>'
    
    return HTMLResponse(page("SQL Console", f"""
<h1>⌨ SQL Console</h1>
<div class="nav">
  <a href="/">Dashboard</a>
  <a href="/db/{db}">Back to DB</a>
</div>
<label>DB: <select onchange="window.location.href='/console?db='+this.value">{db_sel}</select></label>
<form method="get">
<input type="hidden" name="db" value="{db}">
<textarea name="q" style="width:100%;height:120px;margin:8px 0">{q}</textarea>
<button type="submit">Run SQL</button>
</form>
{result}
"""))

@app.get("/connections")
async def connections(db: str = "real_estate"):
    dsn = DB_ALIASES.get(db)
    try:
        conn = get_db(dsn)
        cur = conn.cursor()
        cur.execute("""
            SELECT pid, usename, application_name, client_addr, state, query_start::text, 
                   substring(query,1,80) as query 
            FROM pg_stat_activity WHERE pid<>pg_backend_pid() 
            ORDER BY query_start DESC
        """)
        rows = cur.fetchall()
        conn.close()
        
        thead = "<tr><th>PID</th><th>User</th><th>App</th><th>Client</th><th>State</th><th>Started</th><th>Query</th></tr>"
        tbody = ""
        for r in rows:
            tbody += f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td>{r[5][:16]}</td><td>{r[6]}</td></tr>"
        
        db_sel = "".join(f"<option value='{k}' {'selected' if k==db else ''}>{k}</option>" for k in DB_ALIASES)
        
        return HTMLResponse(page("Connections", f"""
<h1><a href='/' style='color:#94a3b8'>⬅</a> Active Connections</h1>
<label>DB: <select onchange="window.location.href='/connections?db='+this.value">{db_sel}</select></label>
<div class="card"><table>{thead}{tbody}</table></div>
"""))
    except Exception as e:
        return HTMLResponse(page("Error", f"<pre>{e}</pre>"))

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5050
    print(f"🚀 PG Admin at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
