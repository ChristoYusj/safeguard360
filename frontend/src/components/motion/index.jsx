/*
 * SafeGuard 360 - Animation Components
 * Reusable motion primitives using Framer Motion
 */

import { motion, AnimatePresence } from "framer-motion";
import { forwardRef } from "react";

// ═══════════════════════════════════════════════════════════════
// ANIMATION VARIANTS
// ═══════════════════════════════════════════════════════════════

export const fadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};

export const fadeInUp = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
};

export const fadeInDown = {
  initial: { opacity: 0, y: -20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 10 },
};

export const fadeInLeft = {
  initial: { opacity: 0, x: -20 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: 20 },
};

export const fadeInRight = {
  initial: { opacity: 0, x: 20 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -20 },
};

export const scaleIn = {
  initial: { opacity: 0, scale: 0.95 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.95 },
};

export const slideInUp = {
  initial: { y: "100%" },
  animate: { y: 0 },
  exit: { y: "100%" },
};

// Stagger children animation
export const staggerContainer = {
  animate: {
    transition: {
      staggerChildren: 0.05,
      delayChildren: 0.1,
    },
  },
};

export const staggerItem = {
  initial: { opacity: 0, y: 16 },
  animate: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.4,
      ease: [0.25, 0.46, 0.45, 0.94],
    },
  },
};

// ═══════════════════════════════════════════════════════════════
// TRANSITION PRESETS
// ═══════════════════════════════════════════════════════════════

export const transition = {
  fast: { duration: 0.15, ease: [0.4, 0, 0.2, 1] },
  normal: { duration: 0.25, ease: [0.4, 0, 0.2, 1] },
  slow: { duration: 0.4, ease: [0.4, 0, 0.2, 1] },
  spring: { type: "spring", stiffness: 300, damping: 30 },
  bounce: { type: "spring", stiffness: 400, damping: 25 },
};

// ═══════════════════════════════════════════════════════════════
// MOTION COMPONENTS
// ═══════════════════════════════════════════════════════════════

/**
 * FadeIn - Simple fade animation wrapper
 */
export const FadeIn = forwardRef(function FadeIn(
  { children, delay = 0, duration = 0.4, className = "", ...props },
  ref,
) {
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
});

/**
 * FadeInUp - Fade in with upward slide
 */
export const FadeInUp = forwardRef(function FadeInUp(
  {
    children,
    delay = 0,
    duration = 0.5,
    distance = 24,
    className = "",
    ...props
  },
  ref,
) {
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: distance }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -distance / 2 }}
      transition={{ duration, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
});

/**
 * ScaleIn - Scale + fade animation
 */
export const ScaleIn = forwardRef(function ScaleIn(
  { children, delay = 0, duration = 0.4, className = "", ...props },
  ref,
) {
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
});

/**
 * StaggerContainer - Container for staggered children animations
 */
export function StaggerContainer({
  children,
  staggerDelay = 0.05,
  initialDelay = 0.1,
  className = "",
  as = "div",
  ...props
}) {
  const Component = motion[as];

  return (
    <Component
      initial="initial"
      animate="animate"
      exit="exit"
      variants={{
        animate: {
          transition: {
            staggerChildren: staggerDelay,
            delayChildren: initialDelay,
          },
        },
      }}
      className={className}
      {...props}
    >
      {children}
    </Component>
  );
}

/**
 * StaggerItem - Child item for StaggerContainer
 */
export const StaggerItem = forwardRef(function StaggerItem(
  { children, className = "", ...props },
  ref,
) {
  return (
    <motion.div
      ref={ref}
      variants={staggerItem}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
});

/**
 * PageTransition - Wrapper for page-level transitions
 */
export function PageTransition({ children, className = "" }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/**
 * HoverScale - Subtle scale on hover
 */
export function HoverScale({
  children,
  scale = 1.02,
  className = "",
  ...props
}) {
  return (
    <motion.div
      whileHover={{ scale }}
      whileTap={{ scale: 0.98 }}
      transition={transition.fast}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

/**
 * HoverGlow - Adds glow effect on hover via CSS
 */
export function HoverGlow({ children, className = "", ...props }) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={transition.normal}
      className={`card-interactive ${className}`}
      {...props}
    >
      {children}
    </motion.div>
  );
}

/**
 * AnimatedCounter - Animated number counter
 */
export function AnimatedCounter({ value, duration = 1, className = "" }) {
  return (
    <motion.span
      className={className}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      key={value}
    >
      <motion.span
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        {value}
      </motion.span>
    </motion.span>
  );
}

/**
 * Presence - AnimatePresence wrapper with common settings
 */
export function Presence({ children, mode = "wait" }) {
  return <AnimatePresence mode={mode}>{children}</AnimatePresence>;
}

/**
 * SlideIn - Slide in from direction
 */
export function SlideIn({
  children,
  direction = "up",
  delay = 0,
  duration = 0.4,
  className = "",
}) {
  const directions = {
    up: { y: 24 },
    down: { y: -24 },
    left: { x: 24 },
    right: { x: -24 },
  };

  return (
    <motion.div
      initial={{ opacity: 0, ...directions[direction] }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      exit={{ opacity: 0, ...directions[direction] }}
      transition={{ duration, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Re-export core framer-motion utilities
export { motion, AnimatePresence };
