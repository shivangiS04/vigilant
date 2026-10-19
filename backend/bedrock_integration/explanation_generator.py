# Compatibility shim — the rule-based explainer lives in backend.explanation.explainer.
# This alias keeps old import paths working during the transition.
from backend.explanation.explainer import RuleBasedExplainer as ExplanationGenerator

__all__ = ["ExplanationGenerator"]
