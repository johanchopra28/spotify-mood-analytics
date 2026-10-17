* Real plays (30 seconds or more) from the Spotify Extended Streaming History.
* Build the files first:  python -I analysis/build_real_plays.py "<path to my_spotify_data.zip>"
* Then, in Stata, set the working directory to this analysis/ folder and run:  do real_plays.do
* To look at the data yourself afterwards, type:  browse

clear all
set more off
global dir "output"

* ---------------------------------------------------------------- every real play
use "${dir}/real_plays.dta", clear
describe
count
display as text "Real plays: " as result _N

summarize seconds_played, detail
tabulate year
tabulate platform
tabulate reason_end

* the first 15 real plays, in order
sort ts_utc
list ts_ist track artist seconds_played in 1/15, noobs abbreviate(24)

* ---------------------------------------------------------------- one row per song
use "${dir}/real_songs.dta", clear
describe
count
display as text "Distinct songs with at least one real play: " as result _N

summarize n_real_plays, detail

* the 15 most played songs
gsort -n_real_plays -hours_real
list track artist n_real_plays hours_real in 1/15, noobs abbreviate(24)

* the 15 most played artists (by real plays)
collapse (sum) n_real_plays hours_real (count) songs = n_real_plays, by(artist)
gsort -n_real_plays
list artist n_real_plays songs hours_real in 1/15, noobs abbreviate(24)
