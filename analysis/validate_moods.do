* Validation: does the genre-based mood agree with the audio-based mood?
* Same analysis as validate_moods.py. Run export_mood_data.py first to create the CSVs.
*
* Usage: set the working directory to the repo's analysis/ folder, then  do validate_moods.do
*   (or edit the global below)

clear all
set more off
global outdir "output"

foreach level in track artist {

    di _newline as text "=== `level' level ==="
    import delimited "${outdir}/mood_comparison_`level'.csv", clear varnames(1) stringcols(_all)

    * string moods -> numeric codes with a fixed, shared label order
    label define moodlbl 1 "calm" 2 "mellow" 3 "intense" 4 "upbeat", replace
    foreach v in genre_mood audio_mood {
        gen `v'_n = .
        replace `v'_n = 1 if `v' == "calm"
        replace `v'_n = 2 if `v' == "mellow"
        replace `v'_n = 3 if `v' == "intense"
        replace `v'_n = 4 if `v' == "upbeat"
        label values `v'_n moodlbl
    }

    count
    di as text "n = " as result r(N)

    * percent agreement
    gen byte agree = (genre_mood_n == audio_mood_n)
    quietly summarize agree
    di as text "percent agreement = " as result %5.1f 100*r(mean) as text "%"

    * confusion matrix (rows = genre mood, columns = audio mood)
    tabulate genre_mood_n audio_mood_n

    * Cohen's kappa (two raters = the two methods). Undefined if either method uses one label.
    capture noisily kap genre_mood_n audio_mood_n
    if _rc {
        di as error "kappa could not be computed (too few rows or a method uses a single label)"
    }
}
