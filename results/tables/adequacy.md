# Resource adequacy of the German power system, weather years 1991-2025

Solar AC per DC capacity (Energy-Charts 2026): 0.910

## Model checks on the holdout (October 2025 to September 2026)

| model                    |   MAE (% of capacity) |   mean modelled |   mean observed |   daily correlation |   MAE (MW) |   MAPE (%) |
|:-------------------------|----------------------:|----------------:|----------------:|--------------------:|-----------:|-----------:|
| onshore capacity factor  |                  2.38 |           19.1  |           18.96 |                0.98 |      nan   |     nan    |
| offshore capacity factor |                  7.55 |           32.75 |           33.67 |                0.93 |      nan   |     nan    |
| solar capacity factor    |                  1.2  |            9.04 |            8.42 |                0.98 |      nan   |     nan    |
| load (MW)                |                nan    |        53087    |        53692    |                0.96 |     2081.1 |       3.88 |

## Annual capacity factor, observed vs modelled with today's fleet (%)

|   ts_utc |   ('onshore', 'observed') |   ('onshore', 'modelled') |   ('solar', 'observed') |   ('solar', 'modelled') |
|---------:|--------------------------:|--------------------------:|------------------------:|------------------------:|
|     2015 |                      20.5 |                      21.6 |                    11   |                     8.4 |
|     2016 |                      17.6 |                      18.6 |                    10.6 |                     8.2 |
|     2017 |                      20.6 |                      21   |                    10.4 |                     8.2 |
|     2018 |                      19.9 |                      19.4 |                    11.4 |                     8.9 |
|     2019 |                      21.6 |                      21.1 |                    10.7 |                     8.5 |
|     2020 |                      21.9 |                      21.4 |                    10.8 |                     8.5 |
|     2021 |                      18.5 |                      18.5 |                     9.9 |                     8.2 |
|     2022 |                      20.3 |                      20   |                    10.7 |                     8.8 |
|     2023 |                      22.9 |                      22.6 |                     9.2 |                     8.3 |
|     2024 |                      20.7 |                      20.6 |                     8.5 |                     8.1 |
|     2025 |                      18.6 |                      18.5 |                     8.5 |                     8.5 |

## Load model coefficients (weather terms, MW)

|         |   MW per unit |
|:--------|--------------:|
| hdd     |         488.9 |
| hdd_day |         -24   |
| cdd     |         301.7 |
| ghi     |         -10.3 |
| xmas    |       -8658   |

## Scenarios

|                                     |   LOLE h/yr |   EENS GWh/yr | worst year   |   LOLE worst year |   years with LOLE > 2.77 |   new firm capacity for 2.77 h (GW) |   peak net demand (GW) |   mean available firm (GW) |
|:------------------------------------|------------:|--------------:|:-------------|------------------:|-------------------------:|------------------------------------:|-----------------------:|---------------------------:|
| 2026 fleet                          |        0    |          0    | -            |              0    |                        0 |                                0    |                  60.93 |                      74.82 |
| 2030 RES targets, coal at KVBG path |        0    |          0    | -            |              0    |                        0 |                                0    |                  57.79 |                      62.88 |
| 2030, KVBG path, +3 m heat pumps    |        0.27 |          0.16 | 2019.0       |              2.65 |                        0 |                                0    |                  62.6  |                      62.88 |
| 2030, no coal                       |      108.63 |        389.93 | 1996.0       |            196.78 |                       35 |                                9.58 |                  64.3  |                      47.07 |
| 2030, no coal, +3 m heat pumps      |      188.01 |        928.11 | 2010.0       |            319.39 |                       35 |                               14.22 |                  71.19 |                      47.07 |
| 2030, no coal, +6 m heat pumps      |      292.5  |       1818.35 | 2010.0       |            506.72 |                       35 |                               19.47 |                  76.57 |                      47.07 |

## Sensitivities (2030, no coal, +3 m heat pumps)

|                                |   LOLE h/yr |   EENS GWh/yr |   worst year |   LOLE worst year |   years with LOLE > 2.77 |   new firm capacity for 2.77 h (GW) |
|:-------------------------------|------------:|--------------:|-------------:|------------------:|-------------------------:|------------------------------------:|
| central                        |      188.01 |        928.11 |         2010 |            319.39 |                       35 |                               14.22 |
| imports 10 GW in every hour    |       17.53 |         32.68 |         1997 |             81    |                       29 |                                3.67 |
| forced outage rates x 1.5      |      241.93 |       1313.4  |         1996 |            394.55 |                       35 |                               16.42 |
| batteries 10 GW / 20 GWh added |      147.48 |        680.93 |         1996 |            267.54 |                       35 |                               12.28 |
| no storage                     |      307.83 |       1861.45 |         1996 |            487.11 |                       35 |                               20.53 |

## Capacity credit (ELCC), % of added capacity

|                           |   ELCC % |
|:--------------------------|---------:|
| +10 GW onshore            |      5.5 |
| +10 GW offshore           |      4.5 |
| +10 GW solar              |      0.5 |
| +10 GW / 40 GWh batteries |     37.5 |

## When loss of load happens (central case made adequate)

|                                             |   value |
|:--------------------------------------------|--------:|
| share of LOLE in Dec-Feb (%)                |    99.7 |
| share of LOLE between 16 and 20 h local (%) |    51.6 |
| LOLE-weighted temperature (C)               |    -4.8 |
| mean winter temperature, all hours (C)      |     2   |
| LOLE-weighted wind capacity factor (%)      |     4.8 |
| mean winter wind capacity factor (%)        |    30.7 |
| LOLE-weighted heat pump load (GW)           |     4.8 |
| share of LOLE in the 5 worst years (%)      |    65.1 |

## LOLE by weather year (central case made adequate)

|   year |   LOLE h |   EENS GWh |
|-------:|---------:|-----------:|
|   1991 |     0.03 |       0.01 |
|   1992 |     7.58 |       7.87 |
|   1993 |     0    |       0    |
|   1994 |     0    |       0    |
|   1995 |     7.74 |      12.51 |
|   1996 |     5.8  |       3.77 |
|   1997 |    21.85 |      19.3  |
|   1998 |     5.32 |       3.52 |
|   1999 |     0    |       0    |
|   2000 |     4.34 |       3    |
|   2001 |     0.03 |       0.01 |
|   2002 |     1.36 |       0.62 |
|   2003 |    13.67 |      12.19 |
|   2004 |     0.87 |       0.37 |
|   2005 |     0.14 |       0.05 |
|   2006 |     0    |       0    |
|   2007 |     8.89 |       5.2  |
|   2008 |     0    |       0    |
|   2009 |     0.01 |       0    |
|   2010 |     2.55 |       1.24 |
|   2011 |     0    |       0    |
|   2012 |     0.01 |       0    |
|   2013 |     0.28 |       0.1  |
|   2014 |     0    |       0    |
|   2015 |     0.03 |       0.01 |
|   2016 |     0    |       0    |
|   2017 |     0.66 |       0.25 |
|   2018 |     0    |       0    |
|   2019 |    10.61 |      16.69 |
|   2020 |     0    |       0    |
|   2021 |     0    |       0    |
|   2022 |     4.68 |       3.28 |
|   2023 |     0    |       0    |
|   2024 |     0    |       0    |
|   2025 |     0    |       0    |

## Two halves of the record

|                      |   LOLE h/yr |   years with LOLE > 0.5 h |   coldest 72 h mean temperature (C) |
|:---------------------|------------:|--------------------------:|------------------------------------:|
| 1991-2008 (18 years) |        4.31 |                        10 |                               -6.79 |
| 2009-2025 (17 years) |        1.11 |                         4 |                               -5.33 |

|                                   |   per decade |   p (OLS slope) |
|:----------------------------------|-------------:|----------------:|
| coldest 72 h mean temperature (C) |        1.176 |           0.008 |
| LOLE (h)                          |       -1.442 |           0.079 |

Mann-Whitney test, LOLE 1991-2008 vs 2009-2025: p = 0.054

## Renewable droughts: wind + solar below 50% of its daily mean for 3 days or more (2030 fleet)

|                                      |   value |
|:-------------------------------------|--------:|
| drought events of 3 days or more     |   131   |
| per winter (Nov-Feb starts)          |     3.2 |
| share of all days in such events (%) |     3.8 |
| share of LOLE on those days (%)      |    50   |

Longest events:

| start      |   days |   wind + solar (% of mean) |   mean temperature (C) |   LOLE in the event (h) |
|:-----------|-------:|---------------------------:|-----------------------:|------------------------:|
| 1996-12-05 |      9 |                       32.5 |                    0.2 |                     5.4 |
| 1995-10-10 |      7 |                       38.0 |                   14.1 |                     0.0 |
| 1997-01-05 |      7 |                       30.0 |                   -6.1 |                    13.7 |
| 2011-11-17 |      7 |                       35.2 |                    3.6 |                     0.0 |
| 2013-01-11 |      7 |                       37.0 |                   -3.3 |                     0.3 |
| 2006-12-21 |      7 |                       28.8 |                    2.1 |                     0.0 |
| 2001-12-07 |      6 |                       33.7 |                    0.6 |                     0.0 |
| 2007-12-18 |      6 |                       31.2 |                   -2.7 |                     8.9 |
| 2020-11-06 |      6 |                       40.2 |                    6.8 |                     0.0 |
| 2004-11-28 |      6 |                       33.3 |                    3.5 |                     0.0 |

Correlation of observed and modelled annual onshore capacity factors, 2015-2025: 0.94
