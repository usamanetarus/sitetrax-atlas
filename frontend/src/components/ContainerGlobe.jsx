import { Canvas, useFrame, useLoader } from '@react-three/fiber'
import { memo, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AdditiveBlending, BackSide, CanvasTexture, SRGBColorSpace, TextureLoader, Vector3 } from 'three'
import { Package } from './Icons'
import { useTheme } from '../ThemeContext'

const deg = Math.PI / 180
const BASE_ROTATION = 112
const ROTATION_SPEED = 8.5
const DRAG_ROTATION_SPEED = 0.34
const DRAG_TILT_SPEED = 0.005
const MAX_TILT_OFFSET = 0.42
const GLOBE_TILT_X = 0.18
const GLOBE_TILT_Z = -0.08
const GLOBE_RADIUS = 2.38
const EARTH_DAY_TEXTURE = 'https://unpkg.com/three-globe@2.31.0/example/img/earth-day.jpg'
const EARTH_DARK_TEXTURE = 'https://threejs.org/examples/textures/planets/earth_atmos_2048.jpg'

function latLngToSurfacePosition(lat, lng, radius = GLOBE_RADIUS + 0.1) {
  const phi = lat * deg
  const theta = lng * deg
  return [
    Math.cos(phi) * Math.sin(theta) * radius,
    Math.sin(phi) * radius,
    Math.cos(phi) * Math.cos(theta) * radius,
  ]
}

function getRotation(time, startedAt) {
  return ((time - startedAt) / 1000) * ROTATION_SPEED
}

function getSharedRotation(time, startedAt, rotationOffset, reduced) {
  const autoRotation = reduced ? 0 : getRotation(time, startedAt)
  return autoRotation + rotationOffset
}

function smoothstep(edge0, edge1, value) {
  const t = Math.min(Math.max((value - edge0) / (edge1 - edge0), 0), 1)
  return t * t * (3 - 2 * t)
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function getPointerPositionInContainer(event, container) {
  if (!container) return { x: 16, y: 16 }
  const tooltipWidth = 224
  const tooltipHeight = 218
  const edgePadding = 12
  const bottomPadding = 42
  const source = event?.nativeEvent ?? event
  const rect = container.getBoundingClientRect()
  const fallbackX = rect.width / 2
  const fallbackY = rect.height / 2
  const x = Number.isFinite(source?.clientX) ? source.clientX - rect.left : fallbackX
  const y = Number.isFinite(source?.clientY) ? source.clientY - rect.top : fallbackY

  return {
    x: clamp(x + 14, edgePadding, Math.max(edgePadding, rect.width - tooltipWidth - edgePadding)),
    y: clamp(y + 14, edgePadding, Math.max(edgePadding, rect.height - tooltipHeight - bottomPadding)),
  }
}

function getEdgeFadeStyle({ embedded, edge, theme }) {
  const dark = theme === 'dark'
  const directions = {
    top: 'to bottom',
    bottom: 'to top',
    left: 'to right',
    right: 'to left',
  }
  const direction = directions[edge] || directions.bottom
  const side = edge === 'left' || edge === 'right'
  // dark embedded bg is now #08090f = rgba(8,9,15)
  const embeddedDarkSolid = edge === 'bottom' ? 'rgba(8, 9, 15, 0.56)' : 'rgba(8, 9, 15, 0.68)'
  const embeddedDarkMiddle = edge === 'bottom' ? 'rgba(8, 9, 15, 0.12)' : 'rgba(8, 9, 15, 0.18)'
  const embeddedLightSolid = edge === 'bottom' ? 'rgba(255, 255, 255, 0.5)' : 'rgba(255, 255, 255, 0.58)'
  const embeddedLightMiddle = edge === 'bottom' ? 'rgba(255, 255, 255, 0.12)' : 'rgba(255, 255, 255, 0.18)'
  const solid = dark
    ? embedded ? side ? 'rgba(8, 9, 15, 0.72)' : embeddedDarkSolid : 'rgba(8, 9, 15, 0.9)'
    : embedded ? side ? 'rgba(255, 255, 255, 0.6)' : embeddedLightSolid : 'rgba(240, 249, 255, 0.82)'
  const middle = dark
    ? embedded ? side ? 'rgba(8, 9, 15, 0.18)' : embeddedDarkMiddle : 'rgba(8, 9, 15, 0.28)'
    : embedded ? side ? 'rgba(255, 255, 255, 0.16)' : embeddedLightMiddle : 'rgba(240, 249, 255, 0.28)'

  return {
    background: `linear-gradient(${direction}, ${solid}, ${middle} 58%, transparent)`,
  }
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  return reduced
}

function useAnimationStart(reduced) {
  const animationStartRef = useRef(0)

  useEffect(() => {
    if (reduced) {
      animationStartRef.current = 0
    }
  }, [reduced])

  return animationStartRef
}

function hasWebGLSupport() {
  if (typeof document === 'undefined') return true
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
  } catch {
    return false
  }
}

function GlobeFallback({ markers, embedded, theme }) {
  const displayMarkers = markers.slice(0, 6)
  const dark = theme === 'dark'

  return (
    <div className={`absolute inset-0 flex items-center justify-center ${embedded ? 'px-6' : 'px-4'}`}>
      <div className="relative aspect-square w-[min(82%,420px)] max-w-[420px]">
        <div className={`absolute inset-0 rounded-full border ${dark ? 'border-stone-300/10 bg-stone-200/[0.03]' : 'border-stone-200 bg-stone-50/60'} shadow-2xl shadow-stone-950/15`} />
        <div className="absolute inset-[12%] rounded-full border border-stone-300/15" />
        <div className="absolute inset-[25%] rounded-full border border-slate-300/20 dark:border-stone-800" />
        <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-stone-300/10" />
        <div className="absolute left-0 top-1/2 h-px w-full -translate-y-1/2 bg-stone-300/10" />
        <div className="absolute inset-[18%] rounded-full bg-[radial-gradient(circle_at_38%_34%,rgba(96,165,250,0.36),transparent_28%),radial-gradient(circle_at_68%_62%,rgba(37,99,235,0.22),transparent_34%)] blur-sm" />
        {displayMarkers.map((marker, index) => {
          const positions = [
            ['left-[14%]', 'top-[28%]'],
            ['right-[18%]', 'top-[20%]'],
            ['left-[34%]', 'top-[12%]'],
            ['right-[12%]', 'bottom-[28%]'],
            ['left-[20%]', 'bottom-[22%]'],
            ['left-[48%]', 'bottom-[10%]'],
          ][index]
          return (
            <div
              key={marker.label}
              className={`absolute ${positions.join(' ')} h-12 w-12 overflow-hidden rounded-full border-2 border-stone-50 bg-stone-200 shadow-lg shadow-stone-950/20 dark:border-stone-800 dark:bg-stone-950`}
              title={marker.label}
            >
              <img src={marker.src} alt="" className="h-full w-full object-cover" loading="lazy" referrerPolicy="no-referrer" />
            </div>
          )
        })}
      </div>
    </div>
  )
}

function usePinTexture(src, theme) {
  const [texture, setTexture] = useState(null)

  useEffect(() => {
    let cancelled = false
    const image = new Image()
    if (src.startsWith('http') || src.startsWith('//')) {
      image.crossOrigin = 'anonymous'
    }
    image.referrerPolicy = 'no-referrer'
    image.onload = () => {
      if (cancelled) return
      const size = 128
      const canvas = document.createElement('canvas')
      canvas.width = size
      canvas.height = size
      const ctx = canvas.getContext('2d')
      const dark = theme === 'dark'
      const ring = dark ? 'rgba(226, 232, 240, 0.82)' : 'rgba(248, 250, 252, 0.94)'
      const innerRing = dark ? 'rgba(15, 23, 42, 0.34)' : 'rgba(15, 23, 42, 0.12)'
      const overlay = dark ? 'rgba(2, 6, 23, 0.16)' : 'rgba(255, 255, 255, 0)'
      const scale = Math.max(size / image.width, size / image.height)
      const width = image.width * scale
      const height = image.height * scale
      const x = (size - width) / 2
      const y = (size - height) / 2

      ctx.clearRect(0, 0, size, size)
      ctx.beginPath()
      ctx.arc(size / 2, size / 2, size / 2 - 8, 0, Math.PI * 2)
      ctx.fillStyle = ring
      ctx.fill()
      ctx.save()
      ctx.beginPath()
      ctx.arc(size / 2, size / 2, size / 2 - 14, 0, Math.PI * 2)
      ctx.clip()
      ctx.drawImage(image, x, y, width, height)
      ctx.fillStyle = overlay
      ctx.fillRect(0, 0, size, size)
      ctx.restore()
      ctx.beginPath()
      ctx.arc(size / 2, size / 2, size / 2 - 12, 0, Math.PI * 2)
      ctx.lineWidth = 3
      ctx.strokeStyle = innerRing
      ctx.stroke()

      const nextTexture = new CanvasTexture(canvas)
      nextTexture.colorSpace = SRGBColorSpace
      setTexture((previous) => {
        previous?.dispose()
        return nextTexture
      })
    }
    image.src = src

    return () => {
      cancelled = true
      setTexture((previous) => {
        previous?.dispose()
        return null
      })
    }
  }, [src, theme])

  return texture
}

function useGlobeInteraction(rotationOffsetRef, tiltOffsetRef, onInteractStart) {
  const dragRef = useRef({ pointerId: null, startX: 0, startY: 0, startRotationOffset: 0, startTiltOffset: 0 })
  const [dragging, setDragging] = useState(false)

  const endDrag = useCallback((event) => {
    if (dragRef.current.pointerId !== event.pointerId) return
    dragRef.current.pointerId = null
    setDragging(false)
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }, [])

  const handlers = useMemo(() => ({
    onPointerDown: (event) => {
      if (event.button !== undefined && event.button !== 0) return
      onInteractStart()
      dragRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        startRotationOffset: rotationOffsetRef.current,
        startTiltOffset: tiltOffsetRef.current,
      }
      setDragging(true)
      event.currentTarget.setPointerCapture?.(event.pointerId)
      event.preventDefault()
    },
    onPointerMove: (event) => {
      if (dragRef.current.pointerId !== event.pointerId) return
      rotationOffsetRef.current = dragRef.current.startRotationOffset + (event.clientX - dragRef.current.startX) * DRAG_ROTATION_SPEED
      tiltOffsetRef.current = clamp(
        dragRef.current.startTiltOffset + (event.clientY - dragRef.current.startY) * DRAG_TILT_SPEED,
        -MAX_TILT_OFFSET,
        MAX_TILT_OFFSET,
      )
    },
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
    onLostPointerCapture: () => {
      dragRef.current.pointerId = null
      setDragging(false)
    },
  }), [endDrag, onInteractStart, rotationOffsetRef, tiltOffsetRef])

  return { dragging, handlers }
}

function MarkerSprite({ active, marker, onSelect, theme }) {
  const spriteRef = useRef(null)
  const dotRef = useRef(null)
  const texture = usePinTexture(marker.src, theme)
  const position = useMemo(() => latLngToSurfacePosition(marker.lat, marker.lng), [marker.lat, marker.lng])
  const worldPosition = useMemo(() => new Vector3(), [])

  useFrame(() => {
    if (!spriteRef.current) return
    spriteRef.current.getWorldPosition(worldPosition)
    const fade = smoothstep(0.04, 0.4, worldPosition.z / GLOBE_RADIUS)
    const scale = active ? 0.31 : 0.21 + fade * 0.05
    spriteRef.current.material.opacity = fade * (active ? 0.98 : theme === 'dark' ? 0.82 : 0.76)
    spriteRef.current.scale.set(scale, scale, 1)
    if (dotRef.current) {
      dotRef.current.material.opacity = fade * (active ? 0.72 : theme === 'dark' ? 0.46 : 0.34)
    }
  })

  if (!texture) return null

  const stopMarkerEvent = (event) => {
    event.stopPropagation()
    event.nativeEvent?.stopPropagation?.()
  }

  return (
    <group position={position}>
      <sprite
        ref={spriteRef}
        onPointerDown={(event) => {
          stopMarkerEvent(event)
        }}
        onPointerUp={(event) => {
          stopMarkerEvent(event)
          onSelect(marker, event)
        }}
        onClick={(event) => {
          stopMarkerEvent(event)
          onSelect(marker, event)
        }}
        scale={[0.23, 0.23, 1]}
      >
        <spriteMaterial map={texture} transparent opacity={0} depthTest={false} toneMapped={false} />
      </sprite>
      <mesh ref={dotRef} position={[0, -0.145, 0]} scale={0.015}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color={theme === 'dark' ? '#cbd5e1' : '#334155'} transparent opacity={0} depthTest={false} />
      </mesh>
    </group>
  )
}

function GlobeMesh({ activeMarker, animationStartRef, markers, onMarkerSelect, reduced, rotationOffsetRef, theme, tiltOffsetRef }) {
  const groupRef = useRef(null)
  const texture = useLoader(TextureLoader, theme === 'dark' ? EARTH_DARK_TEXTURE : EARTH_DAY_TEXTURE)
  texture.colorSpace = SRGBColorSpace

  useFrame(() => {
    if (!groupRef.current) return
    const time = performance.now()
    if (!animationStartRef.current) animationStartRef.current = time
    const rotation = getSharedRotation(time, animationStartRef.current, rotationOffsetRef.current, reduced)
    groupRef.current.rotation.x = GLOBE_TILT_X + tiltOffsetRef.current
    groupRef.current.rotation.y = (BASE_ROTATION + rotation) * deg
  })

  return (
    <group ref={groupRef} position={[0, -1.08, 0]} rotation={[GLOBE_TILT_X, BASE_ROTATION * deg, GLOBE_TILT_Z]}>
      <mesh>
        <sphereGeometry args={[2.38, 128, 128]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>
      {markers.map((marker) => (
        <MarkerSprite
          key={marker.label}
          active={activeMarker?.label === marker.label}
          marker={marker}
          onSelect={onMarkerSelect}
          theme={theme}
        />
      ))}
      <mesh scale={2.55}>
        <sphereGeometry args={[1, 64, 64]} />
        <meshBasicMaterial
          color="#60a5fa"
          transparent
          opacity={0.1}
          blending={AdditiveBlending}
          side={BackSide}
        />
      </mesh>
    </group>
  )
}

function MarkerTooltip({ marker, onClose, position, theme }) {
  if (!marker) return null
  const cardStyle = {
    left: position?.x ?? 16,
    top: position?.y ?? 16,
    backgroundColor: theme === 'dark' ? 'rgba(2, 6, 23, 0.48)' : 'rgba(255, 255, 255, 0.62)',
    backdropFilter: 'blur(30px) saturate(155%)',
    WebkitBackdropFilter: 'blur(30px) saturate(155%)',
  }

  return (
    <div
      className="absolute z-20 w-56 rounded-lg border border-white/75 p-3 text-left text-stone-950 shadow-2xl shadow-slate-950/15 ring-1 ring-slate-950/[0.04] dark:border-stone-800 dark:text-stone-50 dark:shadow-slate-950/40 dark:ring-stone-900"
      style={cardStyle}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute right-2 top-2 rounded-md px-1.5 py-0.5 text-xs text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:hover:bg-white/10 dark:hover:text-white"
        aria-label="Close container preview"
      >
        x
      </button>
      <div className="mb-2 flex items-center gap-2 pr-6">
        <Package size={16} weight="duotone" className="text-stone-500 dark:text-slate-300" />
        <span className="truncate font-mono text-sm font-semibold">{marker.label}</span>
      </div>
      <div className="mb-2 overflow-hidden rounded-md border border-stone-200 bg-stone-100 dark:border-stone-800 dark:bg-stone-950">
        <img src={marker.src} alt="" className="h-24 w-full object-cover" loading="lazy" referrerPolicy="no-referrer" />
      </div>
      <div className="space-y-1 text-xs leading-5 text-stone-500 dark:text-stone-300">
        <div className="flex justify-between gap-3"><span>Type</span><span className="truncate text-stone-700 dark:text-slate-200">{marker.type}</span></div>
        <div className="flex justify-between gap-3"><span>Status</span><span className="text-stone-700 dark:text-slate-200">{marker.statusCode}</span></div>
        {/*<div className="text-stone-400 dark:text-stone-400">Port-side demo marker</div>*/}
      </div>
    </div>
  )
}

function ContainerGlobe({ embedded = false, markers }) {
  const { theme } = useTheme()
  const reduced = useReducedMotion()
  const [webglSupported, setWebglSupported] = useState(true)
  const animationStartRef = useAnimationStart(reduced)
  const rotationOffsetRef = useRef(0)
  const tiltOffsetRef = useRef(0)
  const containerRef = useRef(null)
  const [activeMarker, setActiveMarker] = useState(null)
  const [previewPosition, setPreviewPosition] = useState({ x: 16, y: 16 })
  const displayMarkers = useMemo(() => markers.filter((marker) => Number.isFinite(marker.lat) && Number.isFinite(marker.lng)), [markers])

  useEffect(() => {
    setWebglSupported(hasWebGLSupport())
  }, [])

  const handleMarkerSelect = useCallback((marker, event) => {
    setPreviewPosition(getPointerPositionInContainer(event, containerRef.current))
    setActiveMarker(marker)
  }, [])
  const { dragging, handlers: interactionHandlers } = useGlobeInteraction(rotationOffsetRef, tiltOffsetRef, () => setActiveMarker(null))
  const containerClass = embedded
    ? `relative h-full min-h-[210px] w-full touch-none overflow-hidden text-left sm:min-h-[380px] lg:min-h-[430px] ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`
    : `relative h-[320px] w-full touch-none overflow-hidden rounded-lg bg-stone-50 text-left shadow-2xl shadow-slate-950/10 dark:bg-stone-950 dark:shadow-slate-950/20 sm:h-[370px] ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`
  const canvasClass = embedded
    ? 'absolute inset-x-[-8%] bottom-[-88px] h-[330px] sm:inset-x-[-16%] sm:bottom-[-118px] sm:h-[470px] lg:bottom-[-112px] lg:h-[520px]'
    : 'absolute inset-x-[-6%] bottom-[-122px] h-[410px]'
  const bottomBlurClass = embedded ? 'h-28 lg:h-32' : 'h-20'
  const bottomFadeClass = embedded ? 'h-24 lg:h-28' : 'h-16'
  const topBlurClass = embedded ? 'h-14 lg:h-16' : 'h-16'
  const topFadeClass = embedded ? 'h-10 lg:h-12' : 'h-12'
  const sideBlurClass = embedded ? 'w-16 lg:w-24' : 'w-12'
  const sideFadeClass = embedded ? 'w-14 lg:w-20' : 'w-10'
  const topFadeStyle = getEdgeFadeStyle({ embedded, edge: 'top', theme })
  const bottomFadeStyle = getEdgeFadeStyle({ embedded, edge: 'bottom', theme })
  const leftFadeStyle = getEdgeFadeStyle({ embedded, edge: 'left', theme })
  const rightFadeStyle = getEdgeFadeStyle({ embedded, edge: 'right', theme })

  return (
    <div
      ref={containerRef}
      className={containerClass}
      {...interactionHandlers}
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_52%_42%,rgba(37,99,235,0.12),transparent_56%)] dark:bg-[radial-gradient(circle_at_52%_42%,rgba(96,165,250,0.13),transparent_56%)]" />
      <div className={canvasClass}>
        {webglSupported ? (
          <Canvas camera={{ position: [0, 0, 5.1], fov: 42 }} dpr={[1, 1.7]} gl={{ antialias: true, alpha: true }}>
            <Suspense fallback={null}>
              <ambientLight intensity={theme === 'dark' ? 1.4 : 2.1} />
              <pointLight position={[3, 3, 5]} intensity={theme === 'dark' ? 4.2 : 5.2} />
              <pointLight position={[-4, -2, 2]} intensity={theme === 'dark' ? 0.85 : 1.4} color="#60a5fa" />
              <GlobeMesh
                activeMarker={activeMarker}
                animationStartRef={animationStartRef}
                markers={displayMarkers}
                onMarkerSelect={handleMarkerSelect}
                reduced={reduced}
                rotationOffsetRef={rotationOffsetRef}
                theme={theme}
                tiltOffsetRef={tiltOffsetRef}
              />
            </Suspense>
          </Canvas>
        ) : (
          <GlobeFallback markers={displayMarkers} embedded={embedded} theme={theme} />
        )}
      </div>
      <div className={`globe-top-blur pointer-events-none absolute inset-x-0 top-0 z-10 ${topBlurClass}`}><span /></div>
      <div className={`pointer-events-none absolute inset-x-0 top-0 z-10 ${topFadeClass}`} style={topFadeStyle} />
      <div className={`globe-bottom-blur pointer-events-none absolute inset-x-0 bottom-0 z-10 ${bottomBlurClass}`}><span /></div>
      <div className={`pointer-events-none absolute inset-x-0 bottom-0 z-10 ${bottomFadeClass}`} style={bottomFadeStyle} />
      <div className={`globe-left-blur pointer-events-none absolute inset-y-0 left-0 z-10 ${sideBlurClass}`}><span /></div>
      <div className={`pointer-events-none absolute inset-y-0 left-0 z-10 ${sideFadeClass}`} style={leftFadeStyle} />
      <div className={`globe-right-blur pointer-events-none absolute inset-y-0 right-0 z-10 ${sideBlurClass}`}><span /></div>
      <div className={`pointer-events-none absolute inset-y-0 right-0 z-10 ${sideFadeClass}`} style={rightFadeStyle} />
      <MarkerTooltip marker={activeMarker} onClose={() => setActiveMarker(null)} position={previewPosition} theme={theme} />
    </div>
  )
}

export default memo(ContainerGlobe)
