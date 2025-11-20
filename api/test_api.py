import requests
import json

def test_federal_register_api():
    base_url = "https://www.federalregister.gov/api/v1/documents.json"
    
    # Test different parameter combinations
    test_cases = [
        {"per_page": 10, "order": "newest"},
        {"conditions[publication_date][gte]": "2024-01-01", "per_page": 5, "order": "newest"},
        {"per_page": 5}  # Minimal case
    ]
    
    for i, params in enumerate(test_cases):
        print(f"\n=== Test Case {i+1} ===")
        print(f"Params: {params}")
        
        try:
            response = requests.get(base_url, params=params, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Total documents: {data.get('total_pages', 'N/A')} pages")
                print(f"Results: {len(data.get('results', []))} documents")
                
                for j, doc in enumerate(data.get('results', [])[:2]):
                    print(f"  Doc {j+1}: {doc.get('title', 'No title')[:60]}...")
            else:
                print(f"Error: {response.text}")
                
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    test_federal_register_api()