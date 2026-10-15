"""Purple-team harness that imitates the closing of an Agilina ceremony.

It feeds a synthetic transcript and a system prompt to a model provider, screens the
exchange with an optional defensive layer and executes the resulting action items with
simulated tools that only record what they were asked to do.
"""

HARNESS_VERSION = "0.2.0"
