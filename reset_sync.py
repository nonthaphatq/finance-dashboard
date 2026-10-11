import sqlite3
conn = sqlite3.connect('finance.db')
conn.execute('UPDATE sync_state SET last_synced_at = NULL WHERE id = 1')
conn.commit()
row = conn.execute('SELECT last_synced_at FROM sync_state').fetchone()
print('sync_state reset to:', row[0])
conn.close()
print('Done')

