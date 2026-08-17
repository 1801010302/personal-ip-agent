"""
Stop handler — EdgeOne Makers
========================================

The file path agents/chat/stop.py is auto-mapped to **POST /chat/stop**.

Given a conversation_id, this triggers the platform runtime's abort flow:
  1. Set the target conversation's cancel signal (asyncio.Event.set()).
  2. Cancel the corresponding asyncio.Task (raises CancelledError).
  3. The streaming loop in index.py observes the signal and calls
     result.cancel() to actually stop the LLM call.

The LLM call is genuinely interrupted — we don't just close the SSE connection.
"""

from .._logger import create_logger

logger = create_logger("stop")


async def handler(context):
    """Abort the running agent for this conversation.

    Goes through ctx.utils.abort_active_run to trigger runtime-level cancellation:
      - Set the target conversation's asyncio.Event signal.
      - Cancel the matching asyncio.Task.
      - context.request.is_cancelled becomes True inside index.py's stream loop.
      - Runner result.cancel() is called to actually terminate the LLM request.
    """
    body = context.request.body or {}
    conversation_id = body.get('conversation_id')
    logger.log(f"conversation_id: {conversation_id}")

    if not conversation_id:
        logger.error('conversation_id is required')
        return {
            'status_code': 400,
            'body': {
                'status': 'error',
                'message': 'conversation_id is required',
            }
        }

    # Trigger platform runtime abort — this actually interrupts the LLM call.
    result = context.utils.abort_active_run(conversation_id)
    logger.log("abort_active_run result:", {
        "aborted": result.aborted,
        "conversation_id": result.conversation_id,
        "run_id": result.run_id,
    })

    return {
        "status": "aborting" if result.aborted else "idle",
        "conversationId": result.conversation_id or conversation_id,
        "runId": result.run_id,
        "aborted": result.aborted,
    }
