"""Initialize PostgreSQL database with test data."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:difyai123456@localhost:5432/dify")

def extract_db_info(database_url: str) -> dict:
    """Extract database connection info from URL."""
    # postgresql://user:password@host:port/dbname
    from urllib.parse import urlparse
    
    parsed = urlparse(database_url)
    return {
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/") if parsed.path else "postgres"
    }

def init_database():
    """Initialize database schema and create test data."""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    db_info = extract_db_info(DATABASE_URL)
    
    print(f"📦 Connecting to PostgreSQL...")
    print(f"   Host: {db_info['host']}:{db_info['port']}")
    print(f"   Database: {db_info['database']}")
    print(f"   User: {db_info['user']}")
    print("")
    
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=db_info['host'],
            port=db_info['port'],
            user=db_info['user'],
            password=db_info['password'],
            database=db_info['database']
        )
        conn.autocommit = False
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("✅ Connected to database")
        print("")
        
        # Create tables
        print("📝 Creating tables...")
        
        # Runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                task_name TEXT NOT NULL,
                module_name TEXT NOT NULL,
                final_score REAL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        print("   ✓ runs table")
        
        # Workflow steps table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                output TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            )
        """)
        print("   ✓ workflow_steps table")
        
        # Assets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            )
        """)
        print("   ✓ assets table")
        
        conn.commit()
        print("✅ Tables created successfully")
        print("")
        
        # Clear existing test data
        print("🗑️  Clearing existing test data...")
        cursor.execute("DELETE FROM assets")
        cursor.execute("DELETE FROM workflow_steps")
        cursor.execute("DELETE FROM runs")
        conn.commit()
        print("✅ Existing data cleared")
        print("")
        
        # Insert test data
        print("📊 Inserting test data...")
        
        # Test run 1
        run_id_1 = "test_run_001"
        cursor.execute("""
            INSERT INTO runs (id, task_name, module_name, final_score, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            run_id_1,
            "launch_coffee_subscription",
            "business_sim",
            95.5,
            "completed",
            "2026-03-27T10:00:00+00:00"
        ))
        
        # Workflow steps for run 1
        cursor.execute("""
            INSERT INTO workflow_steps (id, run_id, step_index, agent_name, prompt, output, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            "step_001_1",
            run_id_1,
            0,
            "market_analyst",
            "Agent: market_analyst\nTask Input: Assess if we should launch a coffee subscription in one city.\nPrevious Output: None\nProduce a short business-focused response.",
            "Market analysis shows strong potential for coffee subscription model. Target urban professionals aged 25-40 with disposable income. Competitor analysis indicates gap in premium subscription market.",
            "2026-03-27T10:00:01+00:00"
        ))
        
        cursor.execute("""
            INSERT INTO workflow_steps (id, run_id, step_index, agent_name, prompt, output, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            "step_001_2",
            run_id_1,
            1,
            "strategy_writer",
            "Agent: strategy_writer\nTask Input: Assess if we should launch a coffee subscription in one city.\nPrevious Output: Market analysis shows strong potential...\nProduce a short business-focused response.",
            "Strategy: Launch premium coffee subscription in Tier 1 cities. Pricing: ¥199/month for daily premium coffee. Marketing focus on convenience and quality. Projected break-even in 6 months.",
            "2026-03-27T10:00:02+00:00"
        ))
        
        # Asset for run 1
        import json
        asset_payload_1 = {
            "summary": "Strategy: Launch premium coffee subscription in Tier 1 cities. Pricing: ¥199/month",
            "score": 95.5,
            "steps": ["market_analyst", "strategy_writer"],
            "recommendation": "proceed",
            "estimated_roi": "25%"
        }
        
        cursor.execute("""
            INSERT INTO assets (id, run_id, asset_type, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "asset_001",
            run_id_1,
            "business_plan",
            json.dumps(asset_payload_1),
            "2026-03-27T10:00:03+00:00"
        ))
        
        print("   ✓ Test run 1: launch_coffee_subscription (score: 95.5)")
        
        # Test run 2
        run_id_2 = "test_run_002"
        cursor.execute("""
            INSERT INTO runs (id, task_name, module_name, final_score, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            run_id_2,
            "evaluate_market_expansion",
            "business_sim",
            88.0,
            "completed",
            "2026-03-27T11:00:00+00:00"
        ))
        
        # Workflow steps for run 2
        cursor.execute("""
            INSERT INTO workflow_steps (id, run_id, step_index, agent_name, prompt, output, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            "step_002_1",
            run_id_2,
            0,
            "market_analyst",
            "Agent: market_analyst\nTask Input: Evaluate expansion to 3 new cities.\nPrevious Output: None\nProduce a short business-focused response.",
            "Expansion analysis: Beijing, Shanghai, Shenzhen show high demand. Combined TAM: 5M potential customers. Infrastructure requirements moderate.",
            "2026-03-27T11:00:01+00:00"
        ))
        
        cursor.execute("""
            INSERT INTO workflow_steps (id, run_id, step_index, agent_name, prompt, output, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            "step_002_2",
            run_id_2,
            1,
            "strategy_writer",
            "Agent: strategy_writer\nTask Input: Evaluate expansion to 3 new cities.\nPrevious Output: Expansion analysis...\nProduce a short business-focused response.",
            "Phased rollout recommended: Q1 Beijing, Q2 Shanghai, Q3 Shenzhen. Budget: ¥50M. Expected customer acquisition: 500K in Year 1.",
            "2026-03-27T11:00:02+00:00"
        ))
        
        # Asset for run 2
        asset_payload_2 = {
            "summary": "Phased rollout to Beijing, Shanghai, Shenzhen. Budget: ¥50M",
            "score": 88.0,
            "steps": ["market_analyst", "strategy_writer"],
            "recommendation": "proceed_with_caution",
            "estimated_roi": "18%",
            "risk_level": "medium"
        }
        
        cursor.execute("""
            INSERT INTO assets (id, run_id, asset_type, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "asset_002",
            run_id_2,
            "business_plan",
            json.dumps(asset_payload_2),
            "2026-03-27T11:00:03+00:00"
        ))
        
        print("   ✓ Test run 2: evaluate_market_expansion (score: 88.0)")
        
        # Test run 3
        run_id_3 = "test_run_003"
        cursor.execute("""
            INSERT INTO runs (id, task_name, module_name, final_score, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            run_id_3,
            "optimize_pricing_strategy",
            "business_sim",
            92.5,
            "completed",
            "2026-03-27T12:00:00+00:00"
        ))
        
        # Workflow steps for run 3
        cursor.execute("""
            INSERT INTO workflow_steps (id, run_id, step_index, agent_name, prompt, output, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            "step_003_1",
            run_id_3,
            0,
            "market_analyst",
            "Agent: market_analyst\nTask Input: Optimize pricing for maximum revenue.\nPrevious Output: None\nProduce a short business-focused response.",
            "Price elasticity analysis: Current ¥199/month shows 15% below optimal. Premium tier at ¥299 could capture 20% of market. Basic tier at ¥149 for price-sensitive segment.",
            "2026-03-27T12:00:01+00:00"
        ))
        
        cursor.execute("""
            INSERT INTO workflow_steps (id, run_id, step_index, agent_name, prompt, output, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            "step_003_2",
            run_id_3,
            1,
            "strategy_writer",
            "Agent: strategy_writer\nTask Input: Optimize pricing for maximum revenue.\nPrevious Output: Price elasticity analysis...\nProduce a short business-focused response.",
            "Recommended pricing tiers: Basic ¥149 (entry-level), Premium ¥199 (standard), Pro ¥299 (premium features). A/B test in 2 cities before national rollout.",
            "2026-03-27T12:00:02+00:00"
        ))
        
        # Asset for run 3
        asset_payload_3 = {
            "summary": "Three-tier pricing: Basic ¥149, Premium ¥199, Pro ¥299",
            "score": 92.5,
            "steps": ["market_analyst", "strategy_writer"],
            "recommendation": "implement",
            "estimated_revenue_increase": "+35%",
            "pricing_tiers": [
                {"name": "Basic", "price": 149},
                {"name": "Premium", "price": 199},
                {"name": "Pro", "price": 299}
            ]
        }
        
        cursor.execute("""
            INSERT INTO assets (id, run_id, asset_type, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "asset_003",
            run_id_3,
            "business_plan",
            json.dumps(asset_payload_3),
            "2026-03-27T12:00:03+00:00"
        ))
        
        print("   ✓ Test run 3: optimize_pricing_strategy (score: 92.5)")
        
        conn.commit()
        
        print("")
        print("✅ Test data inserted successfully")
        print("")
        
        # Verify data
        print("📊 Verifying data...")
        
        cursor.execute("SELECT COUNT(*) as count FROM runs")
        runs_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM workflow_steps")
        steps_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM assets")
        assets_count = cursor.fetchone()['count']
        
        print(f"   ✓ runs: {runs_count}")
        print(f"   ✓ workflow_steps: {steps_count}")
        print(f"   ✓ assets: {assets_count}")
        print("")
        
        cursor.close()
        conn.close()
        
        print("==============================================")
        print("✅ Database initialization completed!")
        print("==============================================")
        print("")
        print("Test data summary:")
        print("  - 3 test runs created")
        print("  - 6 workflow steps recorded")
        print("  - 3 assets generated")
        print("")
        print("You can now test the API:")
        print("  - GET /runs/test_run_001")
        print("  - GET /runs/test_run_002")
        print("  - GET /runs/test_run_003")
        print("  - GET /assets/asset_001")
        print("  - GET /assets/asset_002")
        print("  - GET /assets/asset_003")
        print("")
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        raise
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    init_database()
