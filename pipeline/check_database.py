import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.federal_agent import FederalAgent

async def test_system():
    print("🧪 Testing Federal Agent System...")
    
    agent = FederalAgent()
    
    # Test 1: Database connection
    print("1. Testing database connection...")
    try:
        analysis = await agent._analyze_database_content()
        print(f"✅ Database connected: {analysis.get('total_documents', 0)} documents")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    # Test 2: Search functionality
    print("2. Testing search...")
    try:
        results = await agent._query_mysql("environment", {})
        print(f"✅ Search working: Found {len(results)} results for 'environment'")
    except Exception as e:
        print(f"❌ Search failed: {e}")
        return
    
    # Test 3: Run method
    print("3. Testing run method...")
    try:
        result = await agent.run("environment")
        print(f"✅ Run method working: Returned {len(result)} characters")
    except Exception as e:
        print(f"❌ Run method failed: {e}")
        return
    
    print("🎉 All tests passed! System is working correctly.")

if __name__ == "__main__":
    asyncio.run(test_system())