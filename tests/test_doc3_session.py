"""
Empirical reproducer test for DATABASE_DESIGN.md src/db/session.py undefined symbol.
"""

from scripts.verify_python_blocks import ROOT, extract_python_blocks


def test_doc3_session_init_db_undefined_sa():
    blocks = extract_python_blocks(ROOT / "DATABASE_DESIGN.md")
    session_code = blocks[3]["content"]  # src/db/session.py

    # Check if 'sa' is defined in the block
    assert "import sqlalchemy as sa" not in session_code
    assert "from sqlalchemy import text" not in session_code
    assert "sa.text" in session_code
