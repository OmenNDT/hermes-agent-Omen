/**
 * How a check-in's timing is said, in one place.
 *
 * Home and the Check-in screen both show the same rows, and two independent
 * wordings would eventually disagree about what "due" means — the exact seam
 * this codebase has been closing all along.
 */

export interface CheckInTiming {
  due: boolean;
  days_until: number | null;
  scheduled_at: string;
}

/** The stored shape is an ISO instant; only the day is meaningful to a reader. */
export function day(timestamp: string): string {
  return timestamp.slice(0, 10);
}

export function describeTiming(checkIn: CheckInTiming): string {
  const days = checkIn.days_until;
  if (checkIn.due) {
    if (days !== null && days < -1) return `Quá hẹn ${Math.abs(days)} ngày`;
    if (days === -1) return "Quá hẹn 1 ngày";
    return "Đã tới hẹn nhìn lại";
  }
  if (days === 1) return "Ngày mai";
  if (days !== null) return `Còn ${days} ngày`;
  return `Hẹn nhìn lại ${day(checkIn.scheduled_at)}`;
}
