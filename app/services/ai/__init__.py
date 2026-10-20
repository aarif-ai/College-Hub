"""Document-grounded AI Event Assistant.

Pipeline (each step is its own module so it can be explained and tested):

1. ``extraction``  - read text out of uploaded PDFs (done once, at upload)
2. ``processing``  - turn the official event info + documents into chunks
3. ``retrieval``   - pick the chunks relevant to the question
4. ``provider``    - optional call to an external AI model
5. ``validation``  - reject any answer not supported by the chunks
6. ``assistant``   - orchestrates the steps and the offline demo mode
"""
