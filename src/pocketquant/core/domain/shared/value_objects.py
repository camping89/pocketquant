from pocketquant.core.domain.shared.enums import Interval

INTERVAL_SECONDS = {
    Interval.MINUTE_1: 60,
    Interval.MINUTE_5: 300,
    Interval.MINUTE_15: 900,
    Interval.HOUR_1: 3600,
    Interval.HOUR_4: 14400,
    Interval.DAY_1: 86400,
    Interval.WEEK_1: 604800,
}
