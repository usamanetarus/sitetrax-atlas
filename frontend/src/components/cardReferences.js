export const cardReferenceGroups = {
  statusCodes: {
    label: 'Status codes',
    meaning: 'A0 is clean; A1 is interpolated; I1-I7 are review or low-confidence states.',
    docsUrl: 'https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json',
    websiteUrl: 'https://sitetrax.io/',
  },
  assetHeading: {
    label: 'Asset heading',
    meaning: 'L2R, R2L, U2D, and D2U describe movement in the camera frame.',
    docsUrl: 'https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json',
    websiteUrl: 'https://sitetrax.io/',
  },
  videoCapture: {
    label: 'Video capture',
    meaning: 'Video clips are processed into detections and playback links.',
    docsUrl: 'https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-input-video',
    websiteUrl: 'https://sitetrax.io/products/',
  },
  cameraInstallation: {
    label: 'Camera setup',
    meaning: 'Camera placement and configuration affect detection quality and offline checks.',
    docsUrl: 'https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-input-video',
    websiteUrl: 'https://sitetrax.io/products/',
  },
  videoSchema: {
    label: 'Video fields',
    meaning: 'Video records include clip metadata, timestamps, assets, and camera context.',
    docsUrl: 'https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json',
    websiteUrl: 'https://sitetrax.io/products/',
  },
  facilityOverview: {
    label: 'Facility overview',
    meaning: 'Facility cards summarize recent scans, traffic, health, and exception risk.',
    docsUrl: 'https://docs.sitetrax.io/',
    websiteUrl: 'https://sitetrax.io/products/',
  },
  facilityMetrics: {
    label: 'Facility metrics',
    meaning: 'Metrics show scan volume and trends over a selected time window.',
    docsUrl: 'https://docs.sitetrax.io/',
    websiteUrl: 'https://sitetrax.io/yard-checks-with-sitetrax/',
  },
  detention: {
    label: 'Detention',
    meaning: 'Detention/dwell is inferred from detection history and threshold timing.',
    docsUrl: 'https://sitetrax.io/yard-checks-with-sitetrax/',
    websiteUrl: 'https://sitetrax.io/case-study-intermodal-yard-visibility-solution/',
  },
  operationalInterpretation: {
    label: 'Operational meaning',
    meaning: 'These values are camera-derived estimates, not full lifecycle events.',
    docsUrl: 'https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json',
    websiteUrl: 'https://sitetrax.io/',
  },
  assetSchema: {
    label: 'Asset schema',
    meaning: 'Asset records carry IDs, locations, timestamps, status, camera, and video fields.',
    docsUrl: 'https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json',
    websiteUrl: 'https://docs.sitetrax.io/',
  },
  integrations: {
    label: 'Integrations',
    meaning: 'SiteTrax data can flow into spreadsheets and external systems.',
    docsUrl: 'https://docs.sitetrax.io/books/zapier-integrations',
    websiteUrl: 'https://docs.sitetrax.io/books/google-integrations',
  },
  monitoringRules: {
    label: 'Monitoring rules',
    meaning: 'Rules are watch conditions that trigger alerts when a site event matches.',
    docsUrl: 'https://docs.sitetrax.io/',
    websiteUrl: 'https://sitetrax.io/products/',
  },
  support: {
    label: 'Support',
    meaning: 'Use the docs portal and product pages for setup, troubleshooting, and contact.',
    docsUrl: 'https://docs.sitetrax.io/',
    websiteUrl: 'https://sitetrax.io/products/',
  },
  exportData: {
    label: 'Export data',
    meaning: 'Exports contain live detections and raw asset fields for downstream use.',
    docsUrl: 'https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json',
    websiteUrl: 'https://sitetrax.io/',
  },
  searchResults: {
    label: 'Search results',
    meaning: 'Search returns live asset records filtered by the query and time window.',
    docsUrl: 'https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json',
    websiteUrl: 'https://sitetrax.io/',
  },
}

export const cardReferences = Object.freeze(cardReferenceGroups)
