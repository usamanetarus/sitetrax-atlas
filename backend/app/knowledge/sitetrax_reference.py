"""Compact SiteTrax documentation reference.

This is intentionally small and queryable. It gives the agent stable product and
data-model grounding for conceptual questions, while live operational answers
still go through the SiteTrax API tools.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceEntry:
    title: str
    keywords: tuple[str, ...]
    facts: tuple[str, ...]
    source: str


REFERENCE: tuple[ReferenceEntry, ...] = (
    ReferenceEntry(
        title="SiteTrax purpose",
        keywords=("overview", "what is sitetrax", "ocr", "asset tracking", "supply chain"),
        facts=(
            "SiteTrax is an AI/OCR asset-tracking platform for supply-chain assets such as intermodal containers, chassis, bobtails, trucks, trailers, and custom assets.",
            "The product captures asset IDs, geolocation, timestamps, images, and video-derived evidence using phones, fixed cameras, vehicle-mounted cameras, drones, and compatible camera systems.",
            "Operational value centers on gate automation, proof of drop-off/pickup, yard checks, finding assets, and pushing data into TMS, WMS, ERP, YMS, TOS, spreadsheets, Google Sheets, Slack, visualization tools, or REST endpoints.",
            "The public site positions the product as a no-tags, no-scanners capture workflow for rapid asset visibility.",
        ),
        source="https://sitetrax.io/",
    ),
    ReferenceEntry(
        title="Product modes and capture solutions",
        keywords=("mobile app", "virtual gate", "drive", "drone", "full service", "snap", "quick capture"),
        facts=(
            "SiteTrax product options include Mobile App, Virtual Gate, Drive, Aerial Drone, and Full Service solutions.",
            "Snap.SiteTrax.io is described as a Progressive Web App for quick capture of containers, trailers, and trucks through a browser or QR-code workflow.",
            "The Quick Capture app emphasizes first- and last-mile visibility and allows drivers to capture asset ID and location quickly while in motion.",
            "SiteTrax Mobile is positioned for drayage drivers and yard teams to capture container pickup and drop-off information at yards, ports, and terminals.",
            "SiteTrax Drive is a hands-free, vehicle-mounted camera solution designed to capture supply chain asset data while moving.",
            "The products page says the Mobile App scans asset locations within a facility, the Virtual Gate tracks assets moving in and out of an area, Drive mounts a tablet inside a vehicle with an exterior camera, and Drone supports aerial yard checks.",
            "Full Service packages include complete turnkey capabilities such as power, internet, and hardware.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-snap/page/tutorial-and-introduction-to-snap-from-sitetraxio",
    ),
    ReferenceEntry(
        title="Yard checks and inventory",
        keywords=("yard checks", "inventory", "proof of pickup", "proof of dropoff", "proof of drop-off", "yard visibility"),
        facts=(
            "SiteTrax is designed to replace manual yard checks with camera-driven asset capture.",
            "The public site emphasizes effortless yard checks, automated capture of asset ID, GPS coordinates, timestamps, and images, and timely data delivery to downstream systems.",
            "The platform supports proof of drop-off/pickup and inventory visibility as core workflows for yards, gates, ports, and terminals.",
            "Case-study material describes using SiteTrax data inside a Yard Management System to achieve faster truck turn times and faster yard checks.",
            "The yard-check material emphasizes enhanced visibility into the entire yard inventory and asset location at any time.",
        ),
        source="https://sitetrax.io/yard-checks-with-sitetrax/ and https://sitetrax.io/case-study-intermodal-yard-visibility-solution/",
    ),
    ReferenceEntry(
        title="YMS / 3PL positioning",
        keywords=("yms", "3pl", "yard management system", "competitive advantage", "roi", "logistics management"),
        facts=(
            "The SiteTrax YMS article positions the product as a way to simplify yard visibility, minimize training time, and optimize overall logistics management.",
            "The 3PL page describes SiteTrax as a real-time visibility solution for providers operating in competitive logistics environments.",
            "Public positioning claims a strong ROI, including a '10x ROI' theme in the YMS article.",
            "The basic-and-free YMS article describes using SiteTrax spreadsheets and Google My Maps to generate yard-specific maps from SiteTrax data.",
        ),
        source="https://sitetrax.io/yms/ and https://sitetrax.io/solutions/3pls/",
    ),
    ReferenceEntry(
        title="Digital twin / real-time tracking",
        keywords=("digital twin", "real-time", "real time", "outside the warehouse", "outside the door", "visibility gaps"),
        facts=(
            "SiteTrax describes its platform as creating a digital twin of intermodal assets.",
            "The broader product narrative says the system closes visibility gaps outside the warehouse door, in yards, gates, terminals, and depots.",
            "The platform is presented as delivering real-time identification and tracking for containers, trailers, chassis, flatbeds, trucks, and custom assets.",
        ),
        source="https://sitetrax.io/beyond-containers-2025/ and https://sitetrax.io/supply-chain-wins-with-a-digital-twin/",
    ),
    ReferenceEntry(
        title="Capture and video processing flow",
        keywords=("video", "upload", "processing", "s3", "camera", "input", "capture"),
        facts=(
            "The documented API flow uploads video to a centralized data store, usually Amazon S3, then SiteTrax analyzes the video and pushes extracted asset records to a REST API destination.",
            "Recommended video input is no more than one minute per file, 1920x1080 resolution, 30 FPS, a 6mm or longer lens, MP4 format, and GPS data embedded in subtitles unless the camera is static.",
            "Mobile capture can have many cameras per bucket with dynamic GPS; fixed SiteTrax Gate/stationary cameras use configured/static GPS for the camera/project.",
            "SiteTrax can capture data from Android/mobile cameras and basic security cameras.",
            "Video processing time is proportional to the number of trackable assets in the uploaded video.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-input-video",
    ),
    ReferenceEntry(
        title="Asset record schema",
        keywords=("schema", "payload", "json", "fields", "asset", "record", "api output"),
        facts=(
            "SiteTrax output records represent each detected asset and its metadata.",
            "Core fields include video_name, type, text, datetime, datetime_original, datetime_digitized, gps_lat, gps_lon, container_company, container_country, status, status_code, asset_image, asset_heading, camera, feedback, stacking, and sorting.",
            "text is the detected asset ID. datetime is the time the camera was passing in front of the asset. datetime_original is video creation time. datetime_digitized is when the video was digitized.",
            "stacking pairs container and chassis records when both processing types are selected.",
            "feedback is a record-specific URL useful for feedback or sharing an individual detection.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json",
    ),
    ReferenceEntry(
        title="Asset types",
        keywords=("asset type", "container", "chassis", "generic ocr", "intermodal"),
        facts=(
            "Documented record examples include International Intermodal Shipping Container ID, International Intermodal Shipping Container Chassis, combined Shipping Container and Chassis, and Generic Text Asset Tracking.",
            "For non-container or custom markings, generic OCR records may not include container-specific company/country/status semantics.",
            "Chassis records can be linked to containers through stacking when both are detected and pairing is enabled.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json",
    ),
    ReferenceEntry(
        title="Status codes",
        keywords=("status", "status code", "a0", "a1", "i1", "i2", "i3", "i4", "i5", "i6", "i7", "review"),
        facts=(
            "A0 means no errors were detected for the container entry.",
            "A1 means the check digit was interpolated.",
            "I1 means the BIC repository cannot verify the company of the container.",
            "I2 means the check digit cannot be verified and the record can be treated as incorrect.",
            "I3 means a container was detected but its ID could not be determined, often because of damage, scratches, or a non-standard asset.",
            "I4 means the provided asset database does not contain the listed asset.",
            "I5 can occur when processing container and chassis together and a bare chassis has no matching container.",
            "I6 means low confidence detection. I7 means low confidence detection with an interpolated ID.",
            "Non-A0 records are useful for review queues and exception workflows.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json",
    ),
    ReferenceEntry(
        title="Asset heading and movement",
        keywords=("heading", "asset_heading", "direction", "r2l", "l2r", "u2d", "d2u", "inbound", "outbound"),
        facts=(
            "asset_heading describes direction within the camera frame.",
            "R2L means the asset moved right to left. L2R means left to right. U2D means up to down. D2U means down to up.",
            "At a configured gate, teams may map L2R/R2L to inbound/outbound, but that mapping is camera-position dependent and should be treated as a site convention.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json",
    ),
    ReferenceEntry(
        title="Operational interpretation",
        keywords=("dwell", "detections", "gate pass", "yard inventory", "last seen", "metrics"),
        facts=(
            "Each detection is a camera observation or gate pass, not necessarily a complete lifecycle event by itself.",
            "Last-seen questions should use the newest detection timestamp from the live timeline.",
            "Dwell estimates from camera data are approximate unless paired in/out events are available.",
            "Facility inventory and detention views are inferred from recent detections, headings, and timestamps; they should be explained as camera-derived operational estimates.",
            "The platform’s broader goal is to provide real-time asset visibility that can feed yard management, gate automation, and downstream operational systems.",
        ),
        source="Internal SiteTrax agent operating model derived from SiteTrax API docs and live endpoint behavior.",
    ),
    ReferenceEntry(
        title="Integrations",
        keywords=("integration", "zapier", "chain.io", "tms", "yms", "erp", "wms", "google sheets", "slack", "maps"),
        facts=(
            "SiteTrax data is intended to flow into business systems and integration platforms including Zapier and Chain.io.",
            "The public docs describe pushing live GPS, timestamps, and asset IDs into YMS, TMS, ERP, Google Sheets, Slack, maps, and other downstream tools.",
            "The product site and docs emphasize integration with enterprise systems and automation platforms rather than isolated dashboards.",
            "The brochure and product site describe SiteTrax as a low-infrastructure alternative to expensive OCR gates, GPS devices, and RFID tags.",
            "The about page says asset ID, geolocation, and image data can be pushed in near real-time into TMS, YMS, or other data management systems.",
        ),
        source="https://docs.sitetrax.io/books/zapier-integrations and https://docs.sitetrax.io/books/chainio-integrations",
    ),
    ReferenceEntry(
        title="Google integrations",
        keywords=("google integrations", "google sheets", "google drive", "google maps", "gmail", "my maps"),
        facts=(
            "Google integrations let SiteTrax data move into Google Sheets, Google Drive, Google Maps, and Gmail workflows.",
            "The Google Maps integration is described as a way to import the SiteTrax spreadsheet into Google My Maps and visualize asset locations from GPS coordinates.",
            "The integration requires at least one scanned asset and a spreadsheet populated by SiteTrax.",
        ),
        source="https://docs.sitetrax.io/books/google-integrations",
    ),
    ReferenceEntry(
        title="Troubleshooting and support flow",
        keywords=("status page", "support ticket", "troubleshoot", "troubleshooting", "monitor what you scanned", "not show up"),
        facts=(
            "When records from a video do not show up, SiteTrax tells customers to check the status page and then open a support ticket if services are up.",
            "The Service Portal is used to monitor what was scanned and review the results and sample payloads.",
            "For free accounts, the docs note a typical limit of 100 scans per month and one asset at a time unless continuous scanning is enabled through support.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json/revisions/86 and https://docs.sitetrax.io/books/sitetraxio-snap/page/tutorial-and-introduction-to-snap-from-sitetraxio",
    ),
    ReferenceEntry(
        title="Terms and data handling",
        keywords=("terms", "privacy", "customer content", "ai output", "aggregated data", "license", "support the services"),
        facts=(
            "The Terms of Service define Customer Content as data uploaded or processed by the customer through the Services.",
            "AI Output Data is the processed result of Customer Content, including OCR results, identified asset IDs, and geolocation logs.",
            "Aggregated Data is described as statistical, de-identified, and anonymized data that cannot reasonably be linked to a specific customer or person.",
            "The Terms state SiteTrax may host, copy, process, transmit, and display customer content and AI output data as needed to deliver, secure, support, and improve the services.",
        ),
        source="https://sitetrax.io/tos and https://sitetrax.io/privacy-policy/",
    ),
    ReferenceEntry(
        title="Product positioning",
        keywords=("brochure", "no tags", "no scanners", "real time", "container locations", "turnaround"),
        facts=(
            "The public brochure frames SiteTrax as real-time container tracking that reduces manual data entry.",
            "The site positions the product as a way to avoid expensive gates, GPS tracking devices, and RFID tags while still improving visibility.",
            "The product story repeatedly emphasizes real-time or near-real-time updates of container locations and asset data.",
            "The main site says the workflow is simple to use and deploy, ideal for in/out gates, proof of drop-off/pickup, and efficient yard checks.",
            "The site describes a three-step flow: install camera, capture video, read data.",
        ),
        source="https://sitetrax.io/brochure and https://sitetrax.io/",
    ),
    ReferenceEntry(
        title="Support and contact",
        keywords=("support", "contact", "sales", "documentation portal", "help", "phone", "email"),
        facts=(
            "The products page points users to the documentation portal for existing deployments and says it is available 24/7.",
            "Public contact details include a phone number and sales email on the products page.",
            "The documentation portal is described as the place to browse knowledge-base articles and deployment support content.",
        ),
        source="https://sitetrax.io/products/",
    ),
    ReferenceEntry(
        title="Service portal and projects",
        keywords=("service portal", "projects", "project detail", "project users", "project integrations", "multi-project dashboard"),
        facts=(
            "The Service Portal is the central web app for monitoring, managing, and troubleshooting SiteTrax deployments.",
            "It is where customers review scan results, object lists, project configuration, and sample payloads.",
            "The portal organizes data around projects; each project can have users and integrations attached to it.",
            "The public site also references a multi-project dashboard for viewing multiple locations or capture methods together.",
        ),
        source="https://docs.sitetrax.io/",
    ),
    ReferenceEntry(
        title="Asset gallery and detail pages",
        keywords=("assets gallery", "asset detail", "full payload", "video naming convention", "asset status", "project integrations"),
        facts=(
            "The Assets page is a card-based gallery of detected assets.",
            "Opening an asset card leads to the Asset Detail page, where the full JSON payload is shown at the bottom of the page.",
            "The docs explicitly call out Asset Status and Heading, Asset Types, Project Users, Project Integrations, Projects List, and Video Naming Convention as part of the portal model.",
            "The portal is structured so analysts can move from a gallery view into the raw payload for troubleshooting or validation.",
        ),
        source="https://docs.sitetrax.io/",
    ),
    ReferenceEntry(
        title="Project management pages",
        keywords=("project list", "project users", "project integrations", "project detail", "projects list"),
        facts=(
            "The Projects List page shows all projects the current user can access.",
            "Project Detail is the hub for a single project's configuration and status.",
            "Project Users lists everyone who has access to the project.",
            "Project Integrations shows the configured downstream data integrations for that project.",
        ),
        source="https://docs.sitetrax.io/",
    ),
    ReferenceEntry(
        title="Virtual Gate installation and digital twin",
        keywords=("virtual gate", "gate installation", "digital twin", "motion detection", "camera orientation", "day/night mode"),
        facts=(
            "Virtual Gate deployments rely on video delivery to SiteTrax cloud servers and can be wired to webhook destinations.",
            "SiteTrax tunes motion detection, field of view, camera orientation, and day/night settings for each site.",
            "The service portal presents the Digital Twin results for the objects detected by a Virtual Gate camera, including captured images and original video recordings.",
            "Customers are responsible for infrastructure such as power and internet, and should plan dedicated cameras for different gate directions or lanes when needed.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-gate/page/sitetraxio-gate-camera-installation-requirements-and-guidelines",
    ),
    ReferenceEntry(
        title="Video naming convention",
        keywords=("video naming convention", "video file", "naming convention", "filename", "encoded information"),
        facts=(
            "SiteTrax video files follow a structured naming convention that encodes information about the video.",
            "The naming convention is part of the portal's operational model and helps organize and troubleshoot captures.",
        ),
        source="https://docs.sitetrax.io/",
    ),
    ReferenceEntry(
        title="Transportation and facility coverage",
        keywords=("road", "rail", "maritime", "ports", "terminals", "drayage yards", "manufacturing", "interchange"),
        facts=(
            "SiteTrax positioning extends across road, rail, and maritime transportation methods.",
            "The public site mentions ports and terminals, drayage yards, and manufacturing facilities as target operating environments.",
            "The broader message is that SiteTrax can capture inventory/asset visibility across disparate facilities and transportation modes.",
        ),
        source="https://sitetrax.io/solutions-work-in-progress/ and https://sitetrax.io/test/",
    ),
    ReferenceEntry(
        title="Beyond containers and yard visibility",
        keywords=("beyond containers", "yard visibility", "outside the warehouse door", "asset tracking", "flatbeds", "dwell time"),
        facts=(
            "SiteTrax positions real-time asset tracking as a way to close the biggest visibility gaps outside the warehouse door.",
            "The article explicitly extends the platform beyond containers to trailers, chassis, flatbeds, trucks, and custom assets.",
            "It emphasizes automated gate check-in/out, yard inventory, proof of pickup/delivery, dwell time tracking, and exception detection.",
            "The article frames SiteTrax as device-agnostic and aimed at removing constraints from manual checks, RFID, GPS pucks, and legacy OCR systems.",
        ),
        source="https://sitetrax.io/beyond-containers-2025/",
    ),
    ReferenceEntry(
        title="Multi-project dashboard",
        keywords=("multi-project dashboard", "multiple projects", "multi-site", "multiple locations", "centralized", "standardized"),
        facts=(
            "The multi-project dashboard lets customers organize multiple sites, capture devices, or yard zones within one account.",
            "It keeps data standardized and centralized so reporting and analysis are consistent across locations.",
            "The dashboard is designed for teams managing multiple yards or capture methods who want a single review surface.",
        ),
        source="https://sitetrax.io/multi-project-dashboard/",
    ),
    ReferenceEntry(
        title="CTPAT compliance and security",
        keywords=("ctpat", "compliance", "security", "proof of location", "seal integrity", "customs", "cbp"),
        facts=(
            "The CTPAT article treats SiteTrax data as auditable proof of location for security and compliance workflows.",
            "It calls out virtual gate usage for entry and exit logs and ties that to access control and physical security criteria.",
            "It also describes using Snap for quick, phone-based evidence capture of seals and transfers of custody.",
            "The article presents SiteTrax as a way to support risk assessment and mitigation with centralized, shareable asset movement data.",
        ),
        source="https://sitetrax.io/enhancing-supply-chain-security-using-sitetrax-io-data-for-ctpat-compliance-and-certification/",
    ),
    ReferenceEntry(
        title="Project status banner",
        keywords=("project status banner", "project health", "real-time alerts", "critical alerts", "warnings", "confidence"),
        facts=(
            "The Project Status Banner provides real-time alerts to reflect project health and operational confidence.",
            "It is intended to give customers immediate feedback when a setup issue could affect asset identification or scan quality.",
            "The banner is positioned as a way to stay informed and resolve issues before they affect operations.",
        ),
        source="https://sitetrax.io/project-status/",
    ),
    ReferenceEntry(
        title="Sharing asset records",
        keywords=("sharing feature", "share asset", "share an asset", "share record", "share an asset record", "sharing asset record", "secure link", "external recipients", "proof of delivery", "proof of pickup"),
        facts=(
            "The Sharing Feature lets users send an asset record to external recipients without giving them access to the private SiteTrax account.",
            "Users can generate a secure link from the dashboard and share proof of pickup, delivery, condition, or location.",
            "The feature is positioned as a fast way to get critical asset data into the right hands with less friction.",
        ),
        source="https://sitetrax.io/share/",
    ),
    ReferenceEntry(
        title="Feedback feature",
        keywords=("feedback feature", "incorrect", "correct", "exception case", "review", "camera positioning", "poor lighting"),
        facts=(
            "The Feedback Feature lets users flag scans that may be incorrect or affected by obstructions or poor capture conditions.",
            "It is used to report issues like camera positioning, poor lighting, or other exception cases so the team can review and recommend adjustments.",
            "The feature is framed as proactive quality control for real-world capture conditions.",
        ),
        source="https://sitetrax.io/feedback/",
    ),
    ReferenceEntry(
        title="TMS integration and dispatch",
        keywords=("tms", "dispatch", "route planning", "proof of delivery", "freight", "shipment visibility"),
        facts=(
            "The TMS article says SiteTrax data can improve routing, dispatch, and proof-of-delivery workflows by feeding real-time asset data into a TMS.",
            "It emphasizes real-time location data for trucks, trailers, chassis, and containers.",
            "The article positions SiteTrax as a way to support smarter decisions from drayage through delivery.",
        ),
        source="https://sitetrax.io/tms_efficiency/",
    ),
    ReferenceEntry(
        title="Roboflow comparison",
        keywords=("roboflow", "computer vision", "deployment", "freemium", "logistics-ready", "plug-and-play"),
        facts=(
            "The Roboflow comparison argues SiteTrax is logistics-ready while generic vision platforms still require custom setup.",
            "It emphasizes pre-built workflows for in-gate/out-gate tracking, proof of delivery, yard management, and asset monitoring.",
            "The article frames SiteTrax as the integration glue that turns AI outputs into an immediately usable supply-chain workflow.",
        ),
        source="https://sitetrax.io/?p=9103",
    ),
    ReferenceEntry(
        title="FMCSA transparency and broker records",
        keywords=("fmcsa", "broker", "transparency", "electronic records", "48 hours", "audit trail"),
        facts=(
            "The FMCSA article says SiteTrax creates digital audit trails that support broker transparency requirements.",
            "It focuses on retaining electronic records and being able to share transaction information promptly.",
            "The article treats SiteTrax as a way to capture outside-the-warehouse asset movement data for compliance workflows.",
        ),
        source="https://sitetrax.io/good-data-fmcsa/",
    ),
    ReferenceEntry(
        title="Truck driver detention",
        keywords=("truck driver detention", "detention", "dock congestion", "detention fees", "turn time"),
        facts=(
            "The detention article frames truck driver detention as a supply-chain efficiency problem caused by wait times and dock congestion.",
            "SiteTrax is positioned as part of the solution by providing faster visibility and reducing the time it takes to find and move assets.",
            "The article ties improved visibility to lower detention fees and better yard throughput.",
        ),
        source="https://sitetrax.io/?p=9131",
    ),
    ReferenceEntry(
        title="Terminal operations and TOS",
        keywords=("terminal operations", "tos", "marine", "inland terminals", "vessels", "yard operations"),
        facts=(
            "The terminal-operations article frames SiteTrax as a visibility layer for marine and inland terminals.",
            "It says Terminal Operating Systems are essential but need reliable data, and SiteTrax provides that data for cargo flow and yard operations.",
            "The article connects SiteTrax with keeping vessels on schedule and improving terminal efficiency.",
        ),
        source="https://sitetrax.io/articles/ and https://sitetrax.io/upgrade-terminal-operations/",
    ),
    ReferenceEntry(
        title="AI-as-a-Service framing",
        keywords=("ai-as-a-service", "ai as a service", "computer vision", "ocr platform", "smartphone", "virtual gate"),
        facts=(
            "SiteTrax presents itself as an AI-as-a-Service OCR platform for capturing intermodal asset IDs and geolocation.",
            "The about page says the product can use a smartphone or statically mounted camera to collect IDs and locations throughout the day.",
            "It frames the platform as a lower-cost alternative to manual tracking, RFID, GPS pucks, and expensive gates.",
            "The product story emphasizes that the data can feed TMS, YMS, CMS, or other data management systems in near real time.",
        ),
        source="https://sitetrax.io/about/ and https://sitetrax.io/request-a-demo/",
    ),
    ReferenceEntry(
        title="Container management systems",
        keywords=("cms", "container management system", "container management systems", "lifecycle", "predictive analytics"),
        facts=(
            "SiteTrax describes CMS as software for monitoring, tracking, and managing containers throughout their lifecycle.",
            "The CMS article positions SiteTrax as a technology layer that adds AI asset identification and cloud/IOT flexibility to container management.",
            "The product narrative pairs CMS with real-time visibility and operational decision support.",
        ),
        source="https://sitetrax.io/cms/",
    ),
    ReferenceEntry(
        title="Interchange to last mile",
        keywords=("interchange", "last mile", "drayage", "ports", "terminals", "fleet", "historical data"),
        facts=(
            "SiteTrax frames its AI-as-a-Service platform as improving visibility from interchange to final mile.",
            "The article emphasizes drayage as a major pain point and uses real-time asset data to reduce wait times and delays.",
            "It describes ports and terminals as critical nodes where dwell time and container handling visibility matter.",
            "The narrative says SiteTrax can unify data from smartphones and tablets into actionable historical and real-time views for planning and analysis.",
        ),
        source="https://sitetrax.io/enhancing-supply-chain-visibility-from-interchange-to-last-mile-leveraging-intermodal-with-sitetrax/",
    ),
    ReferenceEntry(
        title="Snap PWA — cross-platform capture",
        keywords=("snap pwa", "ios", "windows", "apple", "cross-platform", "qr code", "browser capture", "progressive web app"),
        facts=(
            "SiteTrax Snap is a Progressive Web App (PWA) accessible via mobile web browser or QR code — no app store install required.",
            "Snap supports Android, iOS, and Windows, making it the recommended option for teams that cannot use the Android-only SiteTrax Mobile app.",
            "Snap embeds GPS coordinates and timestamps automatically into captured videos before upload.",
            "The Snap documentation explicitly states it is for users who need iOS or Windows support, where the native Mobile app is unavailable.",
            "Snap is designed for first- and last-mile quick capture: drivers and yard workers can scan containers, trailers, chassis, and trucks through any supported browser.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-snap",
    ),
    ReferenceEntry(
        title="SiteTrax Mobile — Android capture app",
        keywords=("mobile app", "android", "sitetrax mobile", "driver app", "smartphone capture", "video upload"),
        facts=(
            "SiteTrax Mobile is a dedicated Android application for capturing intermodal asset data from a smartphone or tablet.",
            "The app is used by truck drivers and yard operators to record short videos of containers, trailers, and other assets.",
            "Captured videos upload automatically to the SiteTrax backend for AI processing — GPS, timestamps, and asset IDs are extracted.",
            "SiteTrax Mobile is Android-only; Snap (the PWA) is recommended for iOS and Windows users.",
            "The Mobile app is positioned for drayage drivers and yard teams who need reliable on-site capture without fixed camera infrastructure.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-mobile",
    ),
    ReferenceEntry(
        title="Digital twin — predictive and real-time simulation",
        keywords=("digital twin", "predictive", "simulation", "per asset", "pricing model", "arrival departure", "operational data"),
        facts=(
            "SiteTrax describes the digital twin as 'a virtual, real-time counterpart to your physical supply chain process.'",
            "The platform provides location precision beyond city-level data — it identifies exact terminal locations and predicts arrival/departure times.",
            "Asset condition can be assessed alongside location: users can check the physical state and whereabouts of any container at any time.",
            "SiteTrax's pricing model is per captured asset, not per device or equipment, making it cost-effective for variable capture volumes.",
            "The digital twin supports data sharing across 3,000+ independent intermodal carriers in the network.",
            "Outcomes described include reduced labor costs, increased productivity, and better operational decisions for carriers, brokers, shippers, and customers.",
        ),
        source="https://sitetrax.io/supply-chain-wins-with-a-digital-twin/",
    ),
    ReferenceEntry(
        title="Case study — intermodal yard visibility (Chesapeake VA)",
        keywords=("case study", "results", "truck turn time", "yard checks", "yardspot", "3pl", "chesapeake", "east coast"),
        facts=(
            "A 3PL and drayage company operating a 16-acre, 4-yard facility in Chesapeake, Virginia used SiteTrax to address a 2021 container import surge.",
            "SiteTrax OCR was integrated with YardSpot.io YMS to automatically capture container photos, IDs, timestamps, and locations.",
            "Measured results: truck turn times decreased by up to 6× faster, yard checks decreased by 1/3, and back-office staff saved an average of 3 hours per day.",
            "The case study is the primary published evidence of SiteTrax ROI for 3PL gate and yard operations.",
        ),
        source="https://sitetrax.io/case-study-intermodal-yard-visibility-solution/",
    ),
    ReferenceEntry(
        title="3PL use cases and integrations",
        keywords=("3pl", "third-party logistics", "gate operations", "trucker turnaround", "bco", "carrier management", "warehouse optimization"),
        facts=(
            "For 3PLs, SiteTrax covers gate operations (error-free gate check), yard inventory, trucker turnaround, warehouse optimization, and BCO (Beneficial Cargo Owner) communication.",
            "SiteTrax integrates with all four major 3PL system types: YMS (yard scheduling/dock allocation), CMS (carrier management), WMS (warehouse picking/packing), and TMS (dispatch automation and routing).",
            "The 3PL page positions SiteTrax as going 'beyond visibility' — providing strategic decision support rather than just monitoring.",
            "Key competitive differentiators cited: actionable insights that anticipate problems, reduce operational costs, and make operations more data-driven.",
            "Real-time shipment tracking is surfaced to BCOs (cargo owners) so customers can track their own freight in near real time.",
        ),
        source="https://sitetrax.io/solutions/3pls/",
    ),
    ReferenceEntry(
        title="Gate BYOC — Bring Your Own Camera",
        keywords=("byoc", "bring your own camera", "third-party camera", "compatible camera", "existing camera", "gate camera"),
        facts=(
            "The SiteTrax Virtual Gate supports a Bring Your Own Camera (BYOC) model, allowing customers to integrate compatible third-party cameras instead of procuring SiteTrax-branded hardware.",
            "BYOC is documented under the Gate section of the SiteTrax docs, alongside the standard Camera Installation Requirements and Guidelines.",
            "This model reduces upfront hardware cost and lets customers leverage existing on-site camera infrastructure.",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-gate",
    ),
    ReferenceEntry(
        title="API output fields — full schema",
        keywords=("api fields", "output json", "container_company", "container_country", "asset_image", "feedback url", "sorting", "stacking"),
        facts=(
            "Full output field list: video_name, type, text, datetime, datetime_original, datetime_digitized, gps_lat, gps_lon, asset_image, container_company, container_country, status, status_code, asset_heading, stacking, camera, feedback, sorting.",
            "asset_image is a public URL to the detected asset image.",
            "container_company is derived from the BIC database using the 4-letter owner code.",
            "container_country is the country associated with the container company.",
            "feedback is a unique URL per detection — useful for one-click sharing or feedback submission on that specific record.",
            "stacking links a container detection to a chassis detection when both are captured together.",
            "type field classifies the detected asset (e.g. Horizontal ID, Vertical ID, Chassis, Generic OCR).",
        ),
        source="https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json",
    ),
    ReferenceEntry(
        title="Contact and industry membership",
        keywords=("contact", "phone", "email", "sales", "iana", "intermodal association", "north america"),
        facts=(
            "SiteTrax sales contact: sales@sitetrax.io | phone: +1 (757) 819-4600.",
            "SiteTrax is a member of the Intermodal Association of North America (IANA), reflecting a primary focus on the intermodal logistics sector.",
            "The CEO is Chris Machut, who has presented on 'Using AI to Tackle Intermodal Challenges' at IANA and other industry conferences.",
            "SiteTrax has participated in events including IANA Business Meeting (Kansas City 2025), Manifest 2025 (Las Vegas), Smart Freight Week 2025 (Amsterdam), and SCITC 2024.",
        ),
        source="https://sitetrax.io/products/ and https://sitetrax.io/iana-2025/",
    ),
    ReferenceEntry(
        title="EPA and environmental compliance",
        keywords=("epa", "air pollution", "southern california", "waire", "truck turn time", "warehouse emissions", "indirect source rule"),
        facts=(
            "SiteTrax addresses EPA warehouse indirect source rules in Southern California by helping reduce truck turn times, which are a key metric under the WAIRE (Warehouse Actions and Investments to Reduce Emissions) program.",
            "Shorter truck turn times at warehouses and yards directly lower idling emissions, which count against facility scores in the WAIRE program.",
            "The article positions SiteTrax as a compliance enabler: better yard visibility leads to faster truck movement, reducing air quality violations.",
        ),
        source="https://sitetrax.io/articles/",
    ),
)


def _score(entry: ReferenceEntry, query: str) -> int:
    q = query.lower()
    score = 0
    for keyword in entry.keywords:
        if keyword in q:
            score += 10 if " " in keyword else 4
    for fact in entry.facts:
        for token in q.split():
            if len(token) > 2 and token.strip(".,:;?!") in fact.lower():
                score += 1
    return score


def search_reference(query: str, limit: int = 3) -> list[dict]:
    """Return the most relevant SiteTrax reference entries for a docs/product query."""
    scored = [(entry, _score(entry, query)) for entry in REFERENCE]
    matches = [(entry, score) for entry, score in scored if score > 0]
    if not matches:
        matches = scored
    matches.sort(key=lambda item: item[1], reverse=True)
    return [
        {
            "title": entry.title,
            "facts": list(entry.facts),
            "source": entry.source,
            "score": score,
        }
        for entry, score in matches[: max(1, min(limit, 8))]
    ]
