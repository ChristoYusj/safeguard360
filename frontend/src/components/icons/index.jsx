/*
 * SafeGuard 360 - Icon Components
 * Consistent icon library for the platform
 */

// Base icon wrapper with common props
function Icon({ children, className = "", size = 20, ...props }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      width={size}
      height={size}
      className={className}
      {...props}
    >
      {children}
    </svg>
  );
}

// Navigation icons
export function DriversIcon(props) {
  return (
    <Icon {...props}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.8 18.2v-1.1A4.9 4.9 0 0 1 8.7 12h.6a4.9 4.9 0 0 1 4.9 4.9v1.3" />
      <circle cx="17.5" cy="9" r="2.3" />
      <path d="M15.7 13.2a3.7 3.7 0 0 1 3.5 3.7v1" />
    </Icon>
  );
}

export function SteeringWheelIcon(props) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="3" />
      <path d="M12 5v4M7.05 8.05l2.83 2.83M5 12h4M7.05 15.95l2.83-2.83M12 15v4M16.95 15.95l-2.83-2.83M19 12h-4M16.95 8.05l-2.83 2.83" />
    </Icon>
  );
}

export function AttendanceIcon(props) {
  return (
    <Icon {...props}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.8 18.2v-1.1A4.9 4.9 0 0 1 8.7 12h.6a4.9 4.9 0 0 1 4.9 4.9v1.3" />
      <path d="m16.2 10.8 1.7 1.7 3-3" />
    </Icon>
  );
}

export function InzoneIcon(props) {
  return (
    <Icon {...props}>
      <path d="M12 3.8 20 18.5H4L12 3.8Z" />
      <path d="M12 9v4.3M12 16.8h.01" />
    </Icon>
  );
}

export function LogsIcon(props) {
  return (
    <Icon {...props}>
      <path d="M7 5.5h8M7 10h10M7 14.5h10M5.5 4h13A1.5 1.5 0 0 1 20 5.5v13A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5v-13A1.5 1.5 0 0 1 5.5 4Z" />
    </Icon>
  );
}

export function ChatbotIcon(props) {
  return (
    <Icon {...props}>
      <path d="M6.5 6.3h11a2.2 2.2 0 0 1 2.2 2.2v7.1a2.2 2.2 0 0 1-2.2 2.2h-6.7l-4 3v-3H6.5a2.2 2.2 0 0 1-2.2-2.2V8.5a2.2 2.2 0 0 1 2.2-2.2Z" />
    </Icon>
  );
}

export function GearIcon(props) {
  return (
    <Icon {...props}>
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <circle cx="12" cy="12" r="3" />
    </Icon>
  );
}

export function SettingsIcon(props) {
  return <GearIcon {...props} />;
}

// Theme icons
export function SunIcon(props) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2.3M12 19.2v2.3M4.8 4.8l1.6 1.6M17.6 17.6l1.6 1.6M2.5 12h2.3M19.2 12h2.3M4.8 19.2l1.6-1.6M17.6 6.4l1.6-1.6" />
    </Icon>
  );
}

export function MoonIcon(props) {
  return (
    <Icon {...props}>
      <path d="M20 14.2A7.5 7.5 0 1 1 9.8 4 6.3 6.3 0 0 0 20 14.2Z" />
    </Icon>
  );
}

// UI icons
export function ChevronLeftIcon(props) {
  return (
    <Icon {...props}>
      <path d="M15 6 9 12l6 6" />
    </Icon>
  );
}

export function ChevronRightIcon(props) {
  return (
    <Icon {...props}>
      <path d="m9 6 6 6-6 6" />
    </Icon>
  );
}

export function VideoIcon(props) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="6.5" width="13" height="11" rx="2" />
      <path d="M16.5 10 21 7.5v9L16.5 14" />
    </Icon>
  );
}

export function AlertTriangleIcon(props) {
  return (
    <Icon {...props}>
      <path d="M12 3.8 20 18.5H4L12 3.8Z" />
      <path d="M12 8.7v5" />
      <path d="M12 17h.01" />
    </Icon>
  );
}

export function CheckCircleIcon(props) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="8" />
      <path d="m8.6 12.2 2.1 2.1 4.8-5.1" />
    </Icon>
  );
}

export function InfoIcon(props) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 10.3v5" />
      <path d="M12 7.8h.01" />
    </Icon>
  );
}

export function TruckIcon(props) {
  return (
    <Icon {...props}>
      <path d="M3.5 7.5h10v8h-10zM13.5 10.5h3.2l2.3 2.5v2.5h-5.5z" />
      <circle cx="8" cy="17.5" r="1.7" />
      <circle cx="18" cy="17.5" r="1.7" />
    </Icon>
  );
}

export function ClockIcon(props) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v5l3 2" />
    </Icon>
  );
}

export function MapPinIcon(props) {
  return (
    <Icon {...props}>
      <path d="M12 20s6-5.3 6-10a6 6 0 1 0-12 0c0 4.7 6 10 6 10Z" />
      <circle cx="12" cy="10" r="2.2" />
    </Icon>
  );
}

export function NavigationIcon(props) {
  return (
    <Icon {...props}>
      <path d="M12 4.5 18.5 19l-6.5-3-6.5 3L12 4.5Z" />
    </Icon>
  );
}

export function RefreshIcon(props) {
  return (
    <Icon {...props}>
      <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
    </Icon>
  );
}

export function ExternalLinkIcon(props) {
  return (
    <Icon {...props}>
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </Icon>
  );
}

export function ShieldIcon(props) {
  return (
    <Icon {...props}>
      {/* Outer shield outline - heraldic shape */}
      <path
        d="M12 2.5C12 2.5 7 3.8 4 4.2V10.5C4 16.2 8.5 19.8 12 21.5C15.5 19.8 20 16.2 20 10.5V4.2C17 3.8 12 2.5 12 2.5Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Inner detail stroke for depth */}
      <path
        d="M12 4.8C12 4.8 8.2 5.8 6 6.1V10.8C6 15.2 9.5 17.9 12 19.2C14.5 17.9 18 15.2 18 10.8V6.1C15.8 5.8 12 4.8 12 4.8Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="0.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.5"
      />
    </Icon>
  );
}

export function ActivityIcon(props) {
  return (
    <Icon {...props}>
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </Icon>
  );
}

export function CameraIcon(props) {
  return (
    <Icon {...props}>
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
      <circle cx="12" cy="13" r="4" />
    </Icon>
  );
}

export function UsersIcon(props) {
  return (
    <Icon {...props}>
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </Icon>
  );
}

export function BellIcon(props) {
  return (
    <Icon {...props}>
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </Icon>
  );
}

export function BarChartIcon(props) {
  return (
    <Icon {...props}>
      <line x1="12" y1="20" x2="12" y2="10" />
      <line x1="18" y1="20" x2="18" y2="4" />
      <line x1="6" y1="20" x2="6" y2="16" />
    </Icon>
  );
}

export function CircleIcon(props) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="10" />
    </Icon>
  );
}

// Export all icons as a map for dynamic access
export const icons = {
  drivers: DriversIcon,
  steeringWheel: SteeringWheelIcon,
  attendance: AttendanceIcon,
  inzone: InzoneIcon,
  logs: LogsIcon,
  chatbot: ChatbotIcon,
  settings: SettingsIcon,
  gear: GearIcon,
  sun: SunIcon,
  moon: MoonIcon,
  chevronLeft: ChevronLeftIcon,
  chevronRight: ChevronRightIcon,
  video: VideoIcon,
  alertTriangle: AlertTriangleIcon,
  checkCircle: CheckCircleIcon,
  info: InfoIcon,
  truck: TruckIcon,
  clock: ClockIcon,
  mapPin: MapPinIcon,
  navigation: NavigationIcon,
  refresh: RefreshIcon,
  externalLink: ExternalLinkIcon,
  shield: ShieldIcon,
  activity: ActivityIcon,
  camera: CameraIcon,
  users: UsersIcon,
  bell: BellIcon,
  barChart: BarChartIcon,
  circle: CircleIcon,
};
