# ADR 0009: Streamlit through P1, React + TypeScript static site in P2, no API in 2026

Status: accepted 2026-10-26.

## Context
The v2 UI is page-heavy (slate, game page, season tracker, hypotheses, method). TypeScript/frontend is a learning goal, but approaches must ship first and everything is precomputed weekly.

## Options
1. Streamlit as the product for 2026.
2. React from P1, drop Streamlit now.
3. Streamlit locally through P1 while approaches land; React + TS + Vite static site in P2 reading the same JSON marts.

## Decision
Option 3. `nfl site` writes a versioned JSON contract (`marts/site/`); Streamlit renders it in P1; the React site renders the same files from P2 and is deployed to Firebase Hosting. No API server, database or auth in 2026.

## Consequences
UI work is not duplicated because the JSON contract is the product boundary; Streamlit is disposable. The React site is the public face from P2; before that the public proof is the git-committed lock artifacts and a README scorecard.
