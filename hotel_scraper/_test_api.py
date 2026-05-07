import requests
import time

r = requests.post("http://localhost:5000/api/scrape", json={
    "urls": ["https://hotelhaedo.com/"],
    "use_llm": True
})
print("POST response:", r.json())
job_id = r.json()["job_id"]

print("Waiting for job to complete...")
for i in range(60):
    time.sleep(2)
    s = requests.get(f"http://localhost:5000/api/status/{job_id}").json()
    print(f"[{i*2}s] status={s['status']} | logs={len(s['progress'])} | results={len(s['results'])}")
    for p in s["progress"]:
        print("  LOG:", p)
    if s["status"] == "done":
        print("\nFinal results:", len(s["results"]), "hotels")
        for h in s["results"]:
            print(f"  Hotel: {h['name']} | Rooms: {len(h['rooms'])}")
            for room in h["rooms"][:3]:
                print(f"    - {room['name']} | prices: {room.get('prices', [])} | images: {len(room.get('images', []))}")
        break
