cube(`nyc_taxi_rides`, {
    sql_table: `main.nyc_taxi_rides`,
    data_source: `nyc_taxi`,

    dimensions: {
        dispatching_base_num: {
            sql: `dispatching_base_num`,
            type: `string`,
            primaryKey: true,
        },
        hvfhs_license_num: {
            sql: `hvfhs_license_num`,
            type: `string`,
        },
        originating_base_num: {
            sql: `originating_base_num`,
            type: `string`,
        },
        shared_request_flag: {
            sql: `shared_request_flag`,
            type: `string`,
        },
        shared_match_flag: {
            sql: `shared_match_flag`,
            type: `string`,
        },
        access_a_ride_flag: {
            sql: `access_a_ride_flag`,
            type: `string`,
        },
        wav_request_flag: {
            sql: `wav_request_flag`,
            type: `string`,
        },
        wav_match_flag: {
            sql: `wav_match_flag`,
            type: `string`,
        },
        pu_location_id: {
            sql: `PULocationID`,
            type: `number`,
        },
        do_location_id: {
            sql: `DOLocationID`,
            type: `number`,
        },
        pickup_datetime: {
            sql: `pickup_datetime`,
            type: `time`,
        },
        dropoff_datetime: {
            sql: `dropoff_datetime`,
            type: `time`,
        },
        on_scene_datetime: {
            sql: `on_scene_datetime`,
            type: `time`,
        },
        request_datetime: {
            sql: `request_datetime`,
            type: `time`,
        },
    },

    measures: {
        count: {
            type: `count`,
        },
        total_base_passenger_fare: {
            sql: `base_passenger_fare`,
            type: `sum`,
        },
        total_driver_pay: {
            sql: `driver_pay`,
            type: `sum`,
        },
        total_tolls: {
            sql: `tolls`,
            type: `sum`,
        },
        total_bcf: {
            sql: `bcf`,
            type: `sum`,
        },
        total_sales_tax: {
            sql: `sales_tax`,
            type: `sum`,
        },
        total_congestion_surcharge: {
            sql: `congestion_surcharge`,
            type: `sum`,
        },
        total_airport_fee: {
            sql: `airport_fee`,
            type: `sum`,
        },
        total_tips: {
            sql: `tips`,
            type: `sum`,
        },
        avg_trip_miles: {
            sql: `trip_miles`,
            type: `avg`,
        },
        avg_trip_time: {
            sql: `trip_time`,
            type: `avg`,
        },
    },
});