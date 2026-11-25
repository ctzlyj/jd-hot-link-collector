"""Pure batch decisions; platform state is never inferred from login alone."""
HUMAN_REASONS={'VERIFICATION_REQUIRED','LOGIN_REQUIRED','LOGIN_STATE_UNKNOWN'}
REFUSED_REASONS={'HTTP_403_REFUSED','HTTP_429_RATE_LIMIT','PAGE_FREQUENCY_LIMIT'}
TRANSIENT_REASONS={'REQUEST_TIMEOUT','REQUEST_RESULT_UNKNOWN','INITIAL_RESPONSE_MISSING','REQUEST_ABORTED','NETWORK_ERROR','LOCAL_OR_TRANSPORT_ERROR','TASK_ITEM_PAGE_REQUIRED','PAGE_CHANGED_OR_PENDING'}
# Page-state failures look deterministic but are mostly transient in the field: the
# same product usually loads on a direct retry. They join the three-strikes path
# with a short cooldown instead of stopping the whole authorized batch.
PRODUCT_PAGE_STATE_REASONS={'MAIN_IMAGES_MISSING'}

def stall_cooldown_seconds(reason, round_cooldown, page_state_cooldown):
    """Cooldown before retrying a stalled round; page states retry quickly."""
    if reason in PRODUCT_PAGE_STATE_REASONS:
        return max(0, int(page_state_cooldown))
    return max(0, int(round_cooldown))

def initial_phase(previous):
    phase=previous.get('workPhase') or previous.get('phase')
    return phase if phase in {'HEADERS','SWEEP','RECHECK'} and previous.get('coverageVersion')==2 else 'HEADERS'

def stall_state(previous,key):
    key=list(key)
    count=int(previous.get('stallCount') or 0)+1 if previous.get('stall')==key else 1
    return {'stall':key,'stallCount':count}

def recovery_decision(driver,keeper,now):
    phase=driver.get('phase');reason=driver.get('platformReason') or (driver.get('lastRunner') or {}).get('reason')
    if phase in {'DONE','DONE_WITH_PENDING','AWAITING_PRICE_DECISION','BLOCKED_LOCK','BLOCKED_STALL','BLOCKED_DRIVER','BLOCKED_UNKNOWN','BLOCKED_MATERIAL'}:
        return {'action':'STOP','reason':phase}
    if reason in HUMAN_REASONS:return {'action':'HUMAN_REQUIRED','reason':reason}
    if reason not in REFUSED_REASONS:return {'action':'STOP','reason':reason or 'UNCLASSIFIED'}
    attempts=int(keeper.get('attempts') or 0)
    if attempts>=3:return {'action':'EXHAUSTED','reason':reason}
    return {'action':'WAIT_AND_RESUME','notBefore':now+[3600,5400,7200][attempts],'reason':reason}
