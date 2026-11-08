"""Cancellable SSE collection for structured Qwen tool calls.

The browser still receives validated facts, never incomplete tool arguments.
Cancellation interrupts the async HTTP read, closes this call's transport and
leaves provider billing unknown unless a final usage packet was received.
"""
import asyncio,time,json
from contextlib import suppress
import httpx
from services.generation import checkpoint,context,Cancelled

POLL_SECONDS=.05

def _audit(stage,stats):
    if not stage:return
    from services.agent_store import connect
    from datetime import datetime,timezone
    with connect() as db:
        row=db.execute('SELECT sid FROM generations WHERE id=?',(stage['id'],)).fetchone()
        if row and row[0]:db.execute('INSERT INTO events(session,kind,payload,time) VALUES (?,?,?,?)',(row[0],'model_stream',json.dumps(dict(client_request_id=stage['id'],**stats),ensure_ascii=False),datetime.now(timezone.utc).isoformat()))

async def _collect(factory,messages):
    stage=context.get();stats=dict(streaming=True,chunks=0,cancelled=False,usage=None,usage_complete=False,transport_closed=False);started=time.monotonic()
    worker=watcher=None
    try:
        checkpoint()
        # Dedicated transports avoid sharing a closed stream or event loop with
        # other users. Context managers close them on success and cancellation.
        with httpx.Client(timeout=25) as sync_http:
            async with httpx.AsyncClient(timeout=25) as async_http:
                model=factory(dict(http_client=sync_http,http_async_client=async_http))
                async def consume():
                    checkpoint();combined=None
                    stream=model.astream(messages,stream_usage=True)
                    try:
                        async for chunk in stream:
                            checkpoint();stats['chunks']+=1
                            combined=chunk if combined is None else combined+chunk
                            if getattr(combined,'usage_metadata',None):stats['usage']=combined.usage_metadata
                        checkpoint()
                        if combined is None:raise ValueError('empty_stream')
                        stats['usage_complete']=stats['usage'] is not None
                        return combined
                    finally:
                        await stream.aclose()
                async def monitor():
                    while True:
                        await asyncio.sleep(POLL_SECONDS)
                        await asyncio.to_thread(checkpoint)
                worker=asyncio.create_task(consume())
                if stage:
                    watcher=asyncio.create_task(monitor())
                    done,_=await asyncio.wait([worker,watcher],return_when=asyncio.FIRST_COMPLETED)
                    # A cancellation beats a simultaneous final token.
                    if watcher in done:await watcher
                return await worker
    except Cancelled:
        stats['cancelled']=True;raise
    except asyncio.CancelledError:
        stats['cancelled']=True;raise
    except Exception:
        try:checkpoint()
        except Cancelled:
            stats['cancelled']=True;raise
        raise
    finally:
        # Cancel the reader before exiting: its finally closes the SSE iterator.
        for task in (worker,watcher):
            if task and not task.done():task.cancel()
        for task in (worker,watcher):
            if task:
                with suppress(asyncio.CancelledError,Cancelled,Exception):await task
        stats['transport_closed']=True
        stats['duration_ms']=round((time.monotonic()-started)*1000)
        _audit(stage,stats)

def stream_call(factory,messages):
    checkpoint()
    return asyncio.run(_collect(factory,messages))
