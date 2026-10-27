"""Execute a registered full-budget research run or frozen campaign."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flbench.research import main
if __name__ == "__main__":
    main()
