"""Scheduled agent that discovers cycling events from sources and proposes them to the site.

The agent is a standalone tool (talks to the site over its public REST API, never the Django ORM):
it reads a curated source list, extracts event candidates with an LLM, drops anything already on
the site or previously rejected, caps the number per run, and POSTs the rest as pending
competitions for a human moderator to approve. See agent/README.md.
"""
