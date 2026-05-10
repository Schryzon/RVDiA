import asyncio
import os
from prisma import Prisma
from dotenv import load_dotenv

load_dotenv()

async def main():
    db = Prisma()
    await db.connect()
    print("Connected to DB")
    try:
        # Prisma db push might fail to change dimensions of Unsupported types easily
        # So we do it manually with raw SQL
        print("Altering Memory table...")
        await db.execute_raw('ALTER TABLE "Memory" ALTER COLUMN "embedding" TYPE vector(384);')
        print("Success!")
    except Exception as e:
        print(f"Failed: {e}")
        print("Try to drop and recreate instead...")
        try:
            await db.execute_raw('DROP TABLE IF EXISTS "Memory";')
            print("Dropped table. Next deployment will recreate it automatically.")
        except Exception as e2:
            print(f"Drop failed too: {e2}")
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
