cube(`orders`, {
  sql_table: `main.orders`,

  data_source: `default`,

  joins: {},

  dimensions: {
    order_id: {
      sql: `order_id`,
      type: `string`,
      primary_key: true,
    },
    customer_name: {
      sql: `customer_name`,
      type: `string`,
    },
    customer_email: {
      sql: `customer_email`,
      type: `string`,
    },
    product_name: {
      sql: `product_name`,
      type: `string`,
    },
    product_category: {
      sql: `product_category`,
      type: `string`,
    },
    order_status: {
      sql: `order_status`,
      type: `string`,
    },
    payment_method: {
      sql: `payment_method`,
      type: `string`,
    },
    shipping_address: {
      sql: `shipping_address`,
      type: `string`,
    },
    order_date: {
      sql: `order_date`,
      type: `time`,
    },
    delivery_date: {
      sql: `delivery_date`,
      type: `time`,
    },
  },

  measures: {
    count: {
      type: `count`,
    },
    total_amount: {
      sql: `total_amount`,
      type: `sum`,
    },
    avg_unit_price: {
      sql: `unit_price`,
      type: `avg`,
    },
    total_quantity: {
      sql: `quantity`,
      type: `sum`,
    },
  },

  pre_aggregations: {},
});
