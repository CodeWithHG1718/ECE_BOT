# Conversation regression validation

The reported failed sequence is covered in `bot/test_conversation.py`: `/courses 1-4`, `2`, a second-year topic question, `/courses optio`, then `4`. Each navigation input stays out of semantic search. All year lists include the complete set of curriculum codes under the correct semesters.

An actual local CLI walkthrough was also run with the cached BGE-M3 model, network downloads disabled, and no Telegram or paid API calls:

| Input | Observed result |
|---|---|
| Show me courses of 2nd year at IIT Roorkee in 2026 | All 14 course/slot codes and titles, grouped under Semesters 3 and 4; unverified 2026 applicability disclosed. |
| Which topic should I study? | Year-two course list with available topic highlights; missing syllabus coverage labelled. |
| ECC-201 | Fundamentals of Communication System; six numbered units, source ECN-311 syllabus page 53. |
| 2 | Search resolved to “Random processes and Noise models” with ECC-201 filter, not the number 2. |

The model loaded on CUDA only when the topic was selected. Returned resources:

- Chapter 8: Random Signals and Noise — *An Introduction to Analog and Digital Communications*, second edition.
- Chapter 11: System and Noise Calculations — same book/edition.
- Lecture 38: Random Process — NPTEL Analog Communication.
- Lecture 45: Noise Analysis – AM — NPTEL Analog Communication.

All four recommendations included their stored source links. This validates this conversation path, not every possible free-form request or the current academic applicability of the source documents.
