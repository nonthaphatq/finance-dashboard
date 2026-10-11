from database import get_connection
conn = get_connection()
rows = conn.execute(
    'SELECT ref_no, txn_at, amount_satang, direction, type FROM transactions ORDER BY txn_at'
).fetchall()
print('--- transactions table ---')
for r in rows:
    amt = r['amount_satang'] / 100
    print(f"  {r['txn_at']}  {r['ref_no']}  {amt:.2f} THB  {r['direction']}  {r['type']}")
print(f'Total: {len(rows)} row(s)')
print()
errs = conn.execute('SELECT COUNT(*) FROM parse_errors').fetchone()[0]
print(f'--- parse_errors: {errs} row(s) ---')
conn.close()

