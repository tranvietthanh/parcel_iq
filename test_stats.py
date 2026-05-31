import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://parceliq:devpassword@localhost:5432/parceliq')
    try:
        row = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM properties)                                    AS total_properties,
                (SELECT COUNT(*) FROM property_reports WHERE status = 'READY')       AS reports_ready,
                0                                                                    AS awaiting_review,
                (SELECT COUNT(*) FROM property_reports
                  WHERE status = 'FAILED'
                    AND updated_at > NOW() - INTERVAL '7 days')                     AS failed_7d,
                (SELECT COUNT(DISTINCT lga_id) FROM properties p
                  JOIN property_reports pr ON pr.property_id = p.id
                  WHERE pr.status = 'READY')                                         AS lga_coverage,
                (SELECT COUNT(DISTINCT user_id) FROM credit_ledger
                  WHERE entry_type = 'DOWNLOAD_DEBIT'
                    AND created_at >= date_trunc('month', NOW()))                    AS sales_mtd,
                0.0                                                                   AS revenue_mtd
        """)
        print(dict(row))
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(run())
