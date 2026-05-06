import logging
import sys
from typing import Dict, Any, TypedDict
from pathlib import Path

# Add root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from .intent_classifier import IntentClassifier, EditIntent
from .planner import EditPlanner, ExecutionPlan
from .executor import EditExecutor
from state_manager.state_manager import StateManager

logger = logging.getLogger(__name__)

class EditAgentState(TypedDict):
    run_id: str
    command: str
    current_state_json: Dict[str, Any]
    intent: EditIntent
    plan: ExecutionPlan
    result: Dict[str, Any]
    new_version: int

class EditAgent:
    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.planner = EditPlanner()
        self.executor = EditExecutor()
        self.state_manager = StateManager()
        
        # Create the graph
        self.graph = self._create_graph()

    def _create_graph(self) -> StateGraph:
        """Create the LangGraph workflow."""
        workflow = StateGraph(EditAgentState)
        
        # Add nodes
        workflow.add_node("classify_intent", self._classify_intent)
        workflow.add_node("plan_edit", self._plan_edit)
        workflow.add_node("execute_edit", self._execute_edit)
        workflow.add_node("snapshot_state", self._snapshot_state)
        
        # Add edges
        workflow.set_entry_point("classify_intent")
        workflow.add_edge("classify_intent", "plan_edit")
        workflow.add_edge("plan_edit", "execute_edit")
        workflow.add_edge("execute_edit", "snapshot_state")
        workflow.add_edge("snapshot_state", END)
        
        # Use memory saver for checkpointer
        checkpointer = MemorySaver()
        
        return workflow.compile(checkpointer=checkpointer)

    def _classify_intent(self, state: EditAgentState) -> Dict[str, Any]:
        """Classify the user's edit command."""
        intent_data = self.intent_classifier.classify(state["command"])
        intent = EditIntent(**intent_data)
        logger.info(f"Classified intent: {intent}")
        return {"intent": intent}

    def _plan_edit(self, state: EditAgentState) -> Dict[str, Any]:
        """Create an execution plan for the edit."""
        plan = self.planner.plan(state["intent"], state["current_state_json"])
        logger.info(f"Created plan: {plan}")
        return {"plan": plan}

    def _execute_edit(self, state: EditAgentState) -> Dict[str, Any]:
        """Execute the planned edit."""
        result = self.executor.execute(state["intent"], state["run_id"], state["current_state_json"])
        logger.info(f"Execution result: {result}")
        return {"result": result}

    def _snapshot_state(self, state: EditAgentState) -> Dict[str, Any]:
        """Snapshot the new state after edit."""
        # Use the updated state from result, or current if not updated
        new_state = state["result"].get("updated_state", state["current_state_json"])
        
        # Create snapshot
        snapshot = self.state_manager.snapshot(
            run_id=state["run_id"],
            edit_command=state["command"],
            state_json=new_state,
            asset_paths=["mock_asset_path"]  # TODO: Get actual asset paths
        )
        
        logger.info(f"Created snapshot version {snapshot.version}")
        return {"new_version": snapshot.version}

    def process_edit(self, run_id: str, command: str, current_state_json: Dict[str, Any]) -> Dict[str, Any]:
        """Process an edit command through the agent pipeline."""
        initial_state = {
            "run_id": run_id,
            "command": command,
            "current_state_json": current_state_json,
            "intent": None,
            "plan": None,
            "result": None,
            "new_version": None
        }
        
        # Run the graph with config
        config = {"configurable": {"thread_id": run_id}}
        final_state = self.graph.invoke(initial_state, config=config)
        
        # Return the required fields
        return {
            "new_version": final_state["new_version"],
            "intent": final_state["intent"],
            "plan": final_state["plan"],
            "result": final_state["result"]
        }

if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from pathlib import Path
    import state_manager.storage as storage
    
    # Use temporary database for testing
    test_db = Path("test_edit_agent.db")
    if test_db.exists():
        test_db.unlink()
    storage.db_path = str(test_db)
    storage.init_db()
    
    agent = EditAgent()
    run_id = "test_run_123"
    
    # Initial state
    current_state = {"narrator": "normal", "scene": "bright"}
    
    print("--- Testing Edit Agent with 3 chained commands ---")
    
    # Command 1: Change narrator tone
    print("\n1. Processing: 'Make the narrator sound more dramatic'")
    result1 = agent.process_edit(run_id, "Make the narrator sound more dramatic", current_state)
    print(f"Result: new_version={result1['new_version']}, intent={result1['intent'].intent}, plan={result1['plan'].estimated_impact}")
    current_state = result1['result']['updated_state']
    
    # Command 2: Change scene brightness
    print("\n2. Processing: 'The scene looks too bright'")
    result2 = agent.process_edit(run_id, "The scene looks too bright", current_state)
    print(f"Result: new_version={result2['new_version']}, intent={result2['intent'].intent}, plan={result2['plan'].estimated_impact}")
    current_state = result2['result']['updated_state']
    
    # Command 3: Undo
    print("\n3. Processing: 'Undo that'")
    result3 = agent.process_edit(run_id, "Undo that", current_state)
    print(f"Result: new_version={result3['new_version']}, intent={result3['intent'].intent}, plan={result3['plan'].estimated_impact}")
    
    print("\n--- Checking History ---")
    history = agent.state_manager.history(run_id)
    print(f"Total snapshots: {len(history)}")
    for h in history:
        print(f"v{h.version} | {h.edit_command} | state: {h.state_json}")
    
    # Cleanup
    if test_db.exists():
        test_db.unlink()