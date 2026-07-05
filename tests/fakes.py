"""Shared test doubles for exercising executors without a workflow or LLM."""


class ExplodingAgent:
    """Asserts the no-LLM guarantee: any run() call fails the test."""

    async def run(self, *args, **kwargs):
        raise AssertionError("LLM was called on the fallback path")


class CapturingContext:
    """Stand-in for WorkflowContext that records outputs and messages."""

    def __init__(self):
        self.outputs = []
        self.messages = []
        self.state = {}

    async def yield_output(self, value):
        self.outputs.append(value)

    async def send_message(self, value):
        self.messages.append(value)

    def get_state(self, key):
        return self.state.get(key)

    def set_state(self, key, value):
        self.state[key] = value
