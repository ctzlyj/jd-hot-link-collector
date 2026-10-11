"""Bounded passive wait then authenticated read-only probe; never bypass platform checks."""
from email.utils import parsedate_to_datetime

def retry_after_seconds(value,last):
 if value is None:return 0
 try:
  if str(value).isdigit():return max(0,int(value))
  return max(0,parsedate_to_datetime(str(value)).timestamp()-last)
 except (ValueError,TypeError,OverflowError):return 0

def next_action(reason,attempt,last,retry_after=None):
 if reason in ['VERIFICATION_REQUIRED','LOGIN_REQUIRED','LOGIN_STATE_UNKNOWN']:return {'action':'HUMAN_REQUIRED'}
 if reason in ['REQUEST_RESULT_UNKNOWN','PREVIOUS_REQUEST_STILL_PENDING','PAGE_CHANGED_OR_PENDING']:return {'action':'RECONCILE_REQUIRED'}
 if reason in ['HTTP_403_REFUSED','HTTP_429_RATE_LIMIT']:
  if attempt>=3:return {'action':'STOP_REFUSED'}
  return {'action':'WAIT_AND_PROBE','notBefore':last+max([900,1800,3600][attempt],retry_after_seconds(retry_after,last))}
 if reason=='COOLDOWN_REQUIRED':return {'action':'WAIT_AND_RESUME','notBefore':last+600}
 return {'action':'STOP_UNCLASSIFIED'}
