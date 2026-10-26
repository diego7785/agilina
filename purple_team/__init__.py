"""Purple-team harness that imitates the closing of an Agilina ceremony.

It feeds a synthetic transcript and a system prompt to a model provider, screens the
transcript with an optional input scanner, applies the system policy to the action items
and executes the allowed ones with simulated tools that only record what they were asked to
do.
"""

HARNESS_VERSION = "0.3.0"
