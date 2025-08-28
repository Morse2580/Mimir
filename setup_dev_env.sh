#!/bin/bash
# RegOps Platform Development Environment Setup

set -e

echo "🚀 Setting up RegOps Platform Development Environment..."
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d" " -f2)
echo "🐍 Python version: $python_version"

# Check if we're already in a virtual environment
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "✅ Already in virtual environment: $VIRTUAL_ENV"
else
    echo "📦 Creating virtual environment..."
    
    # Remove existing venv if it exists
    if [ -d "venv" ]; then
        echo "🗑️  Removing existing virtual environment..."
        rm -rf venv
    fi
    
    # Create new virtual environment
    python3 -m venv venv
    
    # Activate virtual environment
    source venv/bin/activate
    echo "✅ Virtual environment created and activated"
fi

# Upgrade pip
echo "⬆️  Upgrading pip..."
python -m pip install --upgrade pip

# Install requirements
echo "📥 Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "🔧 Checking installed packages..."
echo "✅ FastAPI: $(python -c 'import fastapi; print(fastapi.__version__)')"
echo "✅ Redis: $(python -c 'import redis; print(redis.__version__)')"
echo "✅ SQLAlchemy: $(python -c 'import sqlalchemy; print(sqlalchemy.__version__)')"
echo "✅ Pydantic: $(python -c 'import pydantic; print(pydantic.VERSION)')"

echo ""
echo "🧪 Running import tests..."

# Test critical imports
python -c "
import sys
sys.path.append('backend')

# Test PII boundary imports
try:
    from app.parallel.common.core import contains_pii
    print('✅ PII Boundary: Core imports working')
except Exception as e:
    print(f'❌ PII Boundary: {e}')

# Test cost tracking imports
try:
    from app.cost.core import calculate_api_cost
    print('✅ Cost Tracking: Core imports working')
except Exception as e:
    print(f'❌ Cost Tracking: {e}')

# Test shell imports (requires Redis)
try:
    from app.cost.shell import CostTracker
    print('✅ Cost Tracking: Shell imports working (Redis available)')
except Exception as e:
    print(f'⚠️  Cost Tracking Shell: {e}')
    print('   This is expected if Redis server is not running')

print('✅ Python environment setup complete!')
"

echo ""
echo "🎯 Next Steps:"
echo "   1. Start Redis server: brew install redis && brew services start redis"
echo "   2. Start PostgreSQL: brew install postgresql && brew services start postgresql"
echo "   3. Run tests: pytest backend/app/cost/tests/test_core.py -v"
echo "   4. Start development server: uvicorn backend.app.main:app --reload"
echo ""
echo "💡 To activate this environment later:"
echo "   source venv/bin/activate"
echo ""
echo "🚨 Remember: This environment includes all production-ready dependencies"
echo "   for the Belgian RegOps Platform pilot!"