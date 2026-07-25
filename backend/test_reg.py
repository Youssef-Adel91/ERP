import httpx
import asyncio

async def run():
    async with httpx.AsyncClient() as client:
        resp = await client.post('http://localhost:8000/api/v1/auth/register', json={
            'company_name': 'Test Company 11',
            'email': 'test11@example.com',
            'password': 'Password123!',
            'full_name': 'Test Admin'
        })
        print(resp.status_code)
        print(resp.text)

asyncio.run(run())
