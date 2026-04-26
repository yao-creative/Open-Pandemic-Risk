export type MapPoint = {
  x: number
  y: number
}

const APPROXIMATE_POSITIONS: Record<string, MapPoint> = {
  AFG: { x: 64, y: 35 },
  AGO: { x: 49, y: 64 },
  ALB: { x: 49, y: 29 },
  ARG: { x: 27, y: 76 },
  AUS: { x: 84, y: 78 },
  BDI: { x: 55, y: 58 },
  BEN: { x: 44, y: 48 },
  BFA: { x: 41, y: 46 },
  BGD: { x: 70, y: 46 },
  BHS: { x: 22, y: 40 },
  BLZ: { x: 18, y: 45 },
  BRA: { x: 32, y: 61 },
  BWA: { x: 54, y: 74 },
  CAF: { x: 52, y: 50 },
  CAN: { x: 20, y: 18 },
  CHN: { x: 75, y: 31 },
  CIV: { x: 40, y: 49 },
  CMR: { x: 47, y: 51 },
  COD: { x: 50, y: 58 },
  COG: { x: 49, y: 56 },
  COL: { x: 27, y: 50 },
  COM: { x: 61, y: 66 },
  CPV: { x: 34, y: 40 },
  DEU: { x: 50, y: 24 },
  DJI: { x: 58, y: 47 },
  DOM: { x: 26, y: 44 },
  DZA: { x: 47, y: 38 },
  EGY: { x: 54, y: 41 },
  ERI: { x: 57, y: 45 },
  ESP: { x: 44, y: 28 },
  ETH: { x: 56, y: 50 },
  FRA: { x: 47, y: 24 },
  FSM: { x: 86, y: 43 },
  GAB: { x: 47, y: 55 },
  GBR: { x: 45, y: 19 },
  GHA: { x: 41, y: 50 },
  GIN: { x: 37, y: 48 },
  GNB: { x: 37, y: 46 },
  GNQ: { x: 45, y: 52 },
  GUY: { x: 32, y: 56 },
  IDN: { x: 77, y: 61 },
  IND: { x: 67, y: 41 },
  IRN: { x: 60, y: 35 },
  ITA: { x: 50, y: 28 },
  JPN: { x: 83, y: 31 },
  KEN: { x: 55, y: 56 },
  KIR: { x: 91, y: 49 },
  KOR: { x: 80, y: 29 },
  LAO: { x: 74, y: 43 },
  LBR: { x: 37, y: 51 },
  LBY: { x: 49, y: 36 },
  LIE: { x: 49, y: 22 },
  LSO: { x: 56, y: 78 },
  MAR: { x: 42, y: 31 },
  MDA: { x: 55, y: 25 },
  MDG: { x: 61, y: 72 },
  MDV: { x: 67, y: 58 },
  MEX: { x: 20, y: 38 },
  MHL: { x: 91, y: 44 },
  MLI: { x: 41, y: 43 },
  MOZ: { x: 58, y: 68 },
  MRT: { x: 37, y: 39 },
  MUS: { x: 63, y: 76 },
  MWI: { x: 57, y: 65 },
  MYS: { x: 75, y: 57 },
  NAM: { x: 50, y: 75 },
  NER: { x: 43, y: 43 },
  NGA: { x: 46, y: 49 },
  NRU: { x: 92, y: 53 },
  NZL: { x: 90, y: 86 },
  PAK: { x: 64, y: 37 },
  PER: { x: 26, y: 64 },
  PHL: { x: 80, y: 49 },
  PLW: { x: 85, y: 48 },
  PNG: { x: 84, y: 64 },
  RUS: { x: 67, y: 17 },
  SAU: { x: 58, y: 42 },
  SDN: { x: 53, y: 42 },
  SEN: { x: 36, y: 43 },
  SGP: { x: 76, y: 60 },
  SLE: { x: 39, y: 47 },
  SLB: { x: 89, y: 64 },
  SOM: { x: 60, y: 52 },
  SSD: { x: 55, y: 48 },
  STP: { x: 43, y: 52 },
  SUR: { x: 31, y: 57 },
  SVK: { x: 51, y: 23 },
  SWZ: { x: 57, y: 79 },
  SYC: { x: 63, y: 64 },
  SYR: { x: 58, y: 34 },
  TCD: { x: 50, y: 43 },
  TGO: { x: 44, y: 49 },
  THA: { x: 74, y: 50 },
  TJK: { x: 66, y: 33 },
  TLS: { x: 79, y: 67 },
  TON: { x: 93, y: 69 },
  TUR: { x: 55, y: 30 },
  TUV: { x: 87, y: 61 },
  TZA: { x: 56, y: 60 },
  UGA: { x: 54, y: 55 },
  UKR: { x: 56, y: 22 },
  USA: { x: 18, y: 29 },
  VNM: { x: 76, y: 47 },
  VUT: { x: 90, y: 73 },
  WSM: { x: 92, y: 67 },
  YEM: { x: 60, y: 46 },
  ZAF: { x: 50, y: 82 },
  ZMB: { x: 55, y: 67 },
  ZWE: { x: 56, y: 70 }
}

function hashCode(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0
  }
  return hash
}

export function hasCountryPoint(countryCode: string): boolean {
  return Boolean(APPROXIMATE_POSITIONS[countryCode])
}

export function getApproximatePoint(countryCode: string): MapPoint {
  const direct = APPROXIMATE_POSITIONS[countryCode]
  if (direct) return direct

  const hash = hashCode(countryCode)
  return {
    x: 12 + (hash % 76),
    y: 18 + (Math.floor(hash / 97) % 60)
  }
}
