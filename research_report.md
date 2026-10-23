# Departure-Time Differences at Shanghai Hongqiao Airport

## Title page

**Proposed revised research report**

**Research topic:** Recorded scheduled-to-actual departure-time differences by scheduled hour, route and weekday at Shanghai Hongqiao International Airport (SHA)

**Student:** [Add your name]  
**Course:** [Add course name and code]  
**Instructor:** [Add instructor name]  
**Submission date:** [Add date]

**Proposal status:** This report uses a revised scope that removes operating-carrier comparisons because the supplied data contain no verified operating-carrier values. Obtain instructor approval for this change before submission.

**Word count:** See the generated PDF for the main-text word count. The title page and references are excluded.

## 1. Introduction

Airline punctuality is an important passenger concern and an operational challenge for airports and carriers. A flight that departs later than its published schedule may affect passengers, aircraft rotations and later flights. Yet a difference between two timestamps does not, by itself, explain why a flight was late. It can reflect operational conditions, how an event was recorded, schedule padding, or a mismatch between the event and the schedule. A useful research project therefore needs both a clearly defined outcome and an honest account of what the available records can establish.

This report studies records for flights departing Shanghai Hongqiao International Airport (SHA) during 31 local service dates from 22 September through 22 October 2026. The supplied CSV contains 23,705 records for arrivals and departures, including the scheduled departure timestamp, an actual departure timestamp for many flights, the directional route, scheduled local hour, weekday, and status fields. The dataset is useful for exploring how the recorded difference between actual and scheduled departure timestamps varies within this airport and period. It is not a validated operational delay database: every row marks `timing_semantics_verified` as false. In addition, the `operating_carrier` field is blank on every row and `operating_carrier_verified` is false throughout. Consequently, the original proposal's carrier comparison is not answerable from these records as provided.

The approved proposal should be amended before submission to remove the unmeasurable carrier component. This report uses the following proposed revised questions:

1. What is the distribution of the recorded scheduled-to-actual departure timestamp difference for SHA departure records with both timestamps and a known status?
2. How does this recorded difference vary by scheduled local departure hour?
3. Does a morning-versus-evening difference remain when departures are compared within the same directional route and weekday?

The outcome is defined as actual departure timestamp minus scheduled departure timestamp, in minutes. Positive values indicate that the recorded actual timestamp is later than the scheduled timestamp; negative values indicate it is earlier. To avoid overstating measurement validity, the report calls this a **recorded departure-time difference**, not a validated departure delay. The central purpose is descriptive: to summarize the observations and explore within-sample associations, not to estimate the causal effect of congestion, airline identity, or any other unobserved factor.

The analysis has three contributions. First, it documents the skew and extreme values rather than relying only on an average. Second, it presents differences by scheduled hour and explicit morning/evening windows. Third, it compares morning and evening within route-weekday strata and uses a date-cluster bootstrap to describe the uncertainty of that matched contrast. The report also identifies the substantial limitations that constrain any interpretation. In particular, one airport and one month cannot establish seasonal, national, or causal claims; and a timestamp field whose event semantics are unverified cannot support a strong operational punctuality conclusion.

## 2. Literature review

Flight delay research commonly treats delay as a system outcome rather than a simple property of one flight. Flights are scheduled in networks; aircraft and crews operate successive legs; passengers connect between flights; and airport demand varies over time. The relevant literature motivates looking at time-of-day schedules and route differences, while warning against interpreting an observed timestamp association as proof of a particular operational mechanism.

Mayer and Sinai (2003) examine network effects, congestion externalities and hubbing in United States airline markets. They argue that carriers may cluster scheduled flights into short periods to create convenient passenger connections. Their empirical analysis finds that hubbing-related travel-time effects differ between hub and non-hub flights, and that not all additional time should be interpreted as socially wasteful congestion. This is relevant to SHA because scheduled departures are concentrated unevenly across hours, and a comparison by hour may reflect the structure of a schedule bank as well as underlying operational conditions. However, their US network and flight-level analysis does not establish that an hourly pattern in this single-airport CSV is caused by congestion. The present data contain neither runway throughput nor air-traffic-control restrictions, weather, queue length, or connection-bank information.

Research on delay propagation reinforces the need for restraint. Pyrgiotis, Malone, and Odoni (2013) model delay propagation within an airport network and show why flight-level outcomes can be interdependent. A late operating event may have implications beyond the flight on which it is first observed. The SHA records analyzed here do not link a delayed departure to a preceding aircraft rotation, crew duty, connecting passengers, or downstream flight. They therefore cannot identify propagation. This literature is used as conceptual context, not as a mechanism tested by the project.

The airport, route and network perspective is particularly relevant to East Asia. Chen and Lin (2021) examine determinants of flight delays from airport, route and network perspectives across East Asian airports. Their framing supports treating route composition as important rather than comparing aggregate hours without adjustment. If, for example, certain routes have more departures in a particular hour, aggregate hourly differences could be due to route mix. A within-route and weekday comparison is a modest way to reduce that compositional concern with the fields available here. It is not equivalent to controlling for all relevant factors in a multi-airport model, and it cannot remove unobserved confounding.

The distribution of deviations also matters. Means and standard deviations can be sensitive to a small number of unusually large values. Koenker and Bassett's (1978) foundational work on regression quantiles motivates attention to conditional quantiles, not only conditional means. This report therefore gives the median, interquartile range and upper percentiles, and presents early timestamps separately from later ones. The descriptive percentile summaries are not a quantile regression, but they help distinguish the typical observation from the upper tail. Efron's (1979) bootstrap provides a general resampling approach for estimating sampling uncertainty. Because observations on the same local date may share conditions, the report resamples complete dates rather than treating each flight as fully independent. Cameron and Miller (2015) explain the importance of clustered dependence and inference at the level where residual dependence may occur. Here the cluster bootstrap is an exploratory uncertainty summary based on only 31 date clusters, not a guarantee of valid population inference.

Taken together, the literature motivates three design choices: report distributional statistics, examine schedule hour without calling schedule volume a direct congestion measure, and compare similar route-weekday groups. It also makes clear that more complete operational and network data would be needed to explain mechanisms. The present project is intentionally narrower than the cited multi-market and network studies. It uses their concepts to frame the questions, but does not claim to reproduce their causal or structural conclusions.

## 3. Methods

### 3.1 Data and study period

The analysis uses the supplied `sha_master.csv` file. It contains 23,705 flight event records with 31 distinct local dates, from 2026-09-22 to 2026-10-22 inclusive. There are 11,832 rows labelled `departure`. The unit of analysis is one departure event row, not one passenger, aircraft rotation, airline, or airport movement independently verified against an external operational source. Departure `event_id` values are unique in the supplied file.

The key variables are `scheduled_departure_utc`, `actual_departure_utc`, `route`, `local_date`, `local_hour`, `weekday`, and `status_display`. The recorded deviation is calculated from the two UTC timestamps using timezone-aware datetime arithmetic:

**Recorded difference (minutes) = 60 x (actual departure UTC - scheduled departure UTC) in hours.**

Equivalently, the difference in seconds is divided by 60. Since both timestamps are expressed in UTC, the calculation does not rely on local clock conversions. The local scheduled hour, route and weekday are used for grouping. A positive value is a later recorded timestamp; a negative value is earlier. In all 11,560 analysis records, this recomputed value exactly agrees with `timing_difference_minutes` in the CSV. That check confirms arithmetic consistency between fields, but it does not verify what the timestamp means operationally.

### 3.2 Inclusion and exclusion

The primary analysis includes departures with nonblank scheduled and actual departure timestamps and a nonblank, non-`Unknown`, non-`Canceled` status. Of 11,832 departure rows, 246 are marked canceled, 16 have an unknown or blank status, and 10 lack a required timestamp after those status exclusions. This leaves 11,560 records. Canceled flights are excluded because they do not have a completed actual departure in the same sense as an operated departure. Unknown status and missing timestamps are excluded because their deviation cannot be established consistently. The notebook reports these exclusions explicitly.

The CSV has 96 records flagged for identity review, 56 of them departures. Twenty-seven of the included departure records are identity-review flagged. A sensitivity check excluding those 27 records leaves 11,533 observations and does not change the rounded median (17.3 minutes), 90th percentile (35.1 minutes), 95th percentile (55.6 minutes), or maximum (590.0 minutes); the share at least 15 minutes later changes from 59.92% to 59.96%. The main descriptive statistics therefore retain them to avoid an undocumented selection, while route-stratified findings should be read with this flag in mind.

### 3.3 Descriptive analysis

For the full eligible dataset, the report calculates the median, first and third quartiles, interquartile range, 90th and 95th percentiles, minimum and maximum, and the share of records that are earlier, exactly on time by timestamp arithmetic, or later. It also reports the proportions at least 15 and 30 minutes later as descriptive thresholds. The thresholds are not represented as official regulatory delay categories. Early and late deviations are summarized separately because a distribution with a long positive tail can have a mean that does not describe a typical departure.

Hourly summaries group records by scheduled local hour at SHA. For each hour, the analysis reports the number of eligible records and the median and 90th percentile. Scheduled records by hour can describe schedule concentration; they do not directly measure runway or airspace congestion. Morning is defined before inspection as 06:00-11:59, and evening as 17:00-22:59 local time. These windows are selected for a transparent exploratory contrast, not because they are proven operational peak periods. Departures outside these windows are retained in full-day summaries and hourly analysis but omitted from the morning-evening comparison.

### 3.4 Route-weekday matched comparison

For the third question, each eligible departure is assigned to its directional route and weekday, and to morning or evening using the fixed hour ranges above. A route-weekday stratum is included in the matched comparison only when it contains at least five eligible morning and five eligible evening flights. This avoids giving a result to strata where either time window is represented by only a few flights. Within each qualifying stratum, the evening mean is subtracted from the morning mean; the reported overall matched contrast is the unweighted mean of those stratum-specific contrasts. The median contrast and proportion of strata with positive contrasts are also reported to show heterogeneity.

For an exploratory interval, local service dates are resampled as whole clusters with replacement 1,000 times, using seed 4001. Each bootstrap sample retains all records from each sampled date, recreates the route-weekday strata and applies the same five-observation minimum in both windows. The estimate in each replicate is the unweighted mean of eligible stratum contrasts. The 2.5th and 97.5th percentiles of these replicate estimates form the reported percentile interval. Resampling by date recognizes that flights on the same date may share common conditions; however, 31 clusters are few, and the bootstrap cannot correct uncertain outcome measurement, selection, or unobserved confounding.

### 3.5 Carrier scope and reproducibility

The originally proposed comparison included verified operating carrier. The field `operating_carrier` is blank in all 23,705 rows and `operating_carrier_verified` is false in all 23,705. The `airline_display` and `canonical_airline_designator` fields have values, but they are not equivalent to a verified operating-carrier field. They are not substituted as if they were verified. The carrier component is therefore removed from the empirical analysis and the revised question should be approved by the instructor before submission. No carrier-specific conclusions are made.

All analyses are documented in the accompanying Jupyter notebook. It uses the CSV, Python's standard `csv` module, the standard library for dates and summary statistics, and Matplotlib for figures. The notebook includes stated filters, explicit time-window definitions, the cluster-bootstrap seed and a measurement warning. The report's exact data-derived results can be reproduced by running its cells from top to bottom in the project environment.

## 4. Results

### 4.1 Outcome distribution

The eligible sample contains 11,560 departure records. The median recorded departure-time difference is 17.3 minutes later than schedule. The first quartile is 11.4 minutes and the third quartile is 25.6 minutes, giving an interquartile range of 14.2 minutes. The distribution's upper tail is appreciably longer than its central spread: the 90th percentile is 35.1 minutes, the 95th percentile is 55.6 minutes, and the largest observed difference is 590.0 minutes. The minimum is 7.4 minutes earlier than schedule.

[[FIGURE:distribution]]

Only 71 of 11,560 records (0.61%) have a negative timestamp difference; none have an exact zero-minute difference at the stored timestamp precision. The remaining 11,489 (99.39%) have a positive difference. A total of 59.92% are at least 15 minutes later by this arithmetic, and 16.02% are at least 30 minutes later. These percentages describe this observed file under the stated filters. They are not official punctuality rates, because the timing semantics have not been independently confirmed and the file is not established here as a complete population of all scheduled SHA departures.

The very large maximum deserves caution. A 590-minute observation can strongly affect the mean and variance even though it represents a single record. It may be a real extreme, a data-entry or event-linking issue, or another outcome of the unverified timestamp semantics. This analysis does not delete it after seeing its value. Instead, it reports robust summaries and includes the extreme transparently. The mean, 22.1 minutes, is higher than the median, consistent with a right-skewed distribution. It should not be used alone to characterize a typical flight.

### 4.2 Scheduled hour and morning-evening comparison

Hourly medians vary across the 06:00-23:00 scheduled departure hours. The median is lowest at hour 22 (8.1 minutes) and hour 6 (10.9 minutes), and highest at hour 9 (26.2 minutes). The 90th percentile also varies, from 19.1 minutes at hour 6 to 49.5 minutes at hour 19 among the displayed hours; hour 23 has only 94 records, so its upper-percentile estimate is less stable. This is not a monotonic pattern in which each later hour has larger recorded differences. Some afternoon/evening hours have elevated upper tails, but the 22:00-23:00 records show smaller medians and upper quantiles. Differences could reflect route mix, schedule characteristics, or data processes as well as operational conditions.

[[FIGURE:hourly]]

For the predefined broad periods, morning has 4,531 records and evening has 3,406. The morning median is 18.9 minutes, with mean 21.7 minutes and 95th percentile 44.2 minutes. The evening median is 16.0 minutes, mean 22.9 minutes and 95th percentile 72.7 minutes. Thus, the evening median is lower by about 2.9 minutes, while its mean and 95th percentile are higher. This contrast illustrates why a single average or a label such as "evening is worse" would be misleading: the typical recorded difference and upper tail move in different directions.

The hourly and two-window results are descriptive, unadjusted comparisons. They answer whether the observed values differ by scheduled hour in this sample, but not whether hour itself explains the difference. Route and weekday composition can vary with hour, and hourly schedule counts are not direct measurements of congestion. The upper tail may also be influenced by a small number of extreme values, including the maximum noted above.

### 4.3 Comparison within route-weekday strata

There are 173 route-weekday strata with at least five eligible flights in both the morning and evening windows. Within each stratum, the evening mean minus morning mean is averaged with equal weight across strata. The resulting mean matched contrast is +0.13 minutes, effectively zero at the scale of the timestamps and far smaller than the variation among individual flight records. The median stratum-specific contrast is -0.96 minutes. In 45.1% of matched strata, the evening mean is higher than the morning mean; in the others it is not. Thus the direction of the contrast is not consistent across route-weekday groups.

The date-cluster bootstrap percentile interval for the equal-stratum-weighted contrast is -2.64 to +4.48 minutes. This interval includes zero and is narrow relative to the flight-level spread, but it should not be interpreted as definitive evidence of no effect. It summarizes resampling variability under this sample, filter and matched-stratum rule; it cannot account for measurement uncertainty or missing operational predictors. The result is best stated as follows: after matching on directional route and weekday among groups with at least five observations per time window, this dataset shows little average morning-evening difference in the mean recorded timestamp gap, with substantial variation among individual strata.

[[FIGURE:matched]]

### 4.4 Carrier and robustness findings

No carrier result is estimable from the verified operating-carrier field. It is empty for every row and explicitly unverified. The fact that display or airline-designator fields contain labels does not validate the identity of the operating carrier for a flight. It would be inappropriate to rank companies or infer that a passenger should select one carrier based on this file.

Excluding the 27 included records flagged for identity review barely changes the full-sample descriptive distribution at the reported precision. This sensitivity check is reassuring for the overall median and upper percentiles but does not validate all route labels or event identities. The 590-minute maximum remains; the analysis therefore appropriately reports it rather than presenting it as representative. No separate claims about airline, congestion, weather, holidays, cancellations as causal events, or network propagation are supported.

## 5. Discussion and conclusions

The first question finds a highly asymmetric recorded timestamp-gap distribution in the eligible file. A typical observation is later than schedule by 17.3 minutes, but the upper tail is much larger: the 95th percentile is 55.6 minutes and one observation reaches 590.0 minutes. Nearly all eligible records have positive differences, while early recorded timestamps are rare. These facts are useful as a description of the supplied data, but should not be recast as established operational departure-delay performance until the timestamp semantics and data coverage are verified.

The second question finds variation by scheduled local hour rather than a simple, steadily worsening daily pattern. The broad morning/evening comparison gives an apparently mixed result: evening has a lower median but higher mean and 95th percentile. That distinction suggests a heavier evening tail in this sample, not that every evening flight is worse. It also demonstrates the importance of selecting distributional measures before inspecting results. The larger hour-specific values could motivate more data collection but do not show that schedule concentration causes delay. As Mayer and Sinai (2003) explain, clustered schedules may relate to connection patterns and network design, while congestion and system effects require additional information.

The third question checks whether an aggregate time-of-day contrast persists for comparable route-weekday groups. In the 173 matched strata, the equal-weight average evening-minus-morning mean is approximately zero, the median is slightly negative, and fewer than half of strata show a positive contrast. The resampling interval spans small negative and positive values. The aggregate morning-evening pattern therefore does not persist as a clear, consistent difference after this descriptive matching. It is not a formal causal estimate, however. Strata can differ in sample size, schedule, and operational context; equal weighting estimates the average matched stratum, not the average flight. The bootstrap uses 31 dates and should be interpreted as a sensitivity summary.

The carrier part of the earlier proposal cannot be addressed: `operating_carrier` contains no values and the verification field is false throughout. Because the user selected reframing, the project should seek instructor approval to replace the carrier question with the route-weekday matched hour question before treating it as the approved scope. If the instructor requires the original carrier question, the project needs independently verified operating-carrier data and a documented identity-resolution process. The current notebook and report do not silently substitute an unverified display name for an operator.

Several limitations define the strength of the conclusions. First, the outcome is not validated. The computed timestamp subtraction matches the CSV's stored `timing_difference_minutes`, but both may be derived from an event whose operational meaning has not been checked. Second, the data cover only one airport and 31 dates. They cannot represent annual seasonality, unusual disruptions outside the period, or other airports. Third, complete-case filtering omits canceled, unknown-status and timestamp-missing records; if incompleteness is systematically related to performance, the observed distribution may be biased. Fourth, the CSV does not provide weather, air-traffic-control initiatives, runway capacity, aircraft rotations, crew schedules, passenger connections, or a verified carrier. These omissions prevent causal interpretation and full adjustment. Fifth, the 590-minute extreme could be a genuine event or a measurement/linkage anomaly; either possibility matters and further source validation is needed.

The most defensible conclusion is consequently limited but informative: in the supplied SHA records, scheduled-to-actual departure timestamp differences are mostly positive and right-skewed; hourly summaries and the broad morning-evening comparison differ in their central and tail behavior; and the near-zero average evening-minus-morning contrast within qualifying route-weekday strata suggests that the raw contrast is not consistent across comparable groups. These are exploratory findings about recorded timestamps, not validated airline punctuality scores or evidence that time of day causes delay.

For a stronger follow-up study, first verify the definition and provenance of each actual departure event, resolve identity-review flags and establish the observation frame. Obtain verified operating-carrier identifiers if carrier comparison remains a project objective. Extend collection across multiple months and, ideally, seasons; collect weather, airport restrictions and schedule/aircraft rotation context; and define inclusion rules before analysis. A larger design could then estimate route and hour associations using an appropriate multilevel or fixed-effects model, report uncertainty clustered at a defensible operational unit, and distinguish a descriptive passenger-facing question from causal claims about congestion. Until then, the report should be submitted as a transparent exploratory analysis and the proposed revision should be cleared with the instructor.

## References

Cameron, A. C., & Miller, D. L. (2015). A practitioner's guide to cluster-robust inference. *Journal of Human Resources, 50*(2), 317-372. https://doi.org/10.3368/jhr.50.2.317

Chen, Y.-H., & Lin, J.-J. (2021). Determinants of flight delays at East Asian airports from an airport, route and network perspective. *Journal of Air Transport Management, 94*, 102064. https://doi.org/10.1016/j.jairtraman.2021.102064

Efron, B. (1979). Bootstrap methods: Another look at the jackknife. *The Annals of Statistics, 7*(1), 1-26. https://doi.org/10.1214/aos/1176344552

Koenker, R., & Bassett, G., Jr. (1978). Regression quantiles. *Econometrica, 46*(1), 33-50. https://doi.org/10.2307/1913643

Mayer, C., & Sinai, T. (2003). Network effects, congestion externalities, and air traffic delays: Or why not all delays are evil. *American Economic Review, 93*(4), 1194-1215. https://doi.org/10.1257/000282803769206269

Pyrgiotis, N., Malone, K. M., & Odoni, A. (2013). Modelling delay propagation within an airport network. *Transportation Research Part C: Emerging Technologies, 27*, 60-75. https://doi.org/10.1016/j.trc.2011.05.017

SHA flight dataset. (2026). *sha_master.csv* [User-supplied flight event dataset, accessed 23 October 2026]. Supplied with the course project workspace. Source URLs and retrieval timestamps are included in the CSV; measurement semantics and operating-carrier identities are not verified in the supplied records.
