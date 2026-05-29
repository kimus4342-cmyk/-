from dotenv import load_dotenv
load_dotenv()
from research_agent import run_topic_proposal
candidates = run_topic_proposal()
for i, c in enumerate(candidates, 1):
    print(f"{i}. [{c.get('type','?')}] {c.get('topic')} / {c.get('angle')} / {c.get('reason')}")
